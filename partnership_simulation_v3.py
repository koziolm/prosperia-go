import sys
import re
import random
import json

# --- Phase 1: Setup and Configuration ---

# Core Simulation Parameters
SIMULATION_YEARS = 5
KSEF_YEAR_NEW_CLIENTS = 100  # Aggressive target for the first year
ANNUAL_GROWTH_RATE = 0.30  # 30% increase in new client acquisition each year after Y1
OPTIMA_PREFERENCE = 0.15 # 15% of new clients choose on-premise (Optima)
ON_PREMISE_VS_CLOUD_PREFERENCE = 0.80 # 80% of Optima clients choose on-premise

# Discount and Commission Data (from previous versions)
OPTIMA_DISCOUNT_TIERS = {
    "software": [
        {"min_sales": 0, "max_sales": 23499, "discount": 0.20},
        {"min_sales": 23500, "max_sales": 46999, "discount": 0.25},
        {"min_sales": 47000, "max_sales": 96999, "discount": 0.30},
        {"min_sales": 97000, "max_sales": 164999, "discount": 0.35},
        {"min_sales": 165000, "max_sales": 299999, "discount": 0.40},
        {"min_sales": 300000, "max_sales": float('inf'), "discount": 0.45},
    ],
    "upgrade_offset": 0.15,
}
XT_COMMISSION = {"year_1": 0.25, "year_2_plus": 0.15}

# Pre-configured Optima Packages
OPTIMA_PACKAGES_BY_SIZE = {
    "Mikrofirma": {
        "modules": ["Faktury", "Księga Podatkowa", "CRM"],
        "probability": 0.50 # 50% of clients are Mikrofirma
    },
    "Mala Firma": {
        "modules": ["Handel Plus", "Księga Handlowa Plus", "Płace i Kadry Plus"],
        "probability": 0.30 # 30% of clients are Mala Firma
    },
    "Srednia Firma": {
        "modules": ["Handel Plus", "Księga Handlowa Plus", "Płace i Kadry Plus", "Analizy Business Intelligence", "Obieg Dokumentów"],
        "probability": 0.20 # 20% of clients are Srednia Firma
    }
}

# Pre-configured Optima Packages (now based on size)

# --- Data Parsing Functions (from v2) ---

def parse_cennik_md(filepath):
    products = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Warning: Price file not found: {filepath}")
        return products

    for line in lines:
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if not cells or len(cells) < 2 or '---' in cells[0] or 'Cena netto' in cells[0] or 'Nazwa modułu' in cells[0]:
            continue

        product_name = cells[0]
        stacjonarnie_price_str_raw = cells[1]
        chmura_price_str_raw = cells[2] if len(cells) > 2 else '' # Handle cases where cloud price might be missing

        # Helper to parse price strings
        def parse_price(price_str_raw):
            match = re.search(r'([\d\s,]+)', price_str_raw)
            if match:
                price_str = match.group(1).strip().replace(' ', '').replace(',', '.')
                if price_str.count('.') > 1:
                    price_str = price_str.replace('.', '', price_str.count('.') - 1)
                try:
                    return float(price_str)
                except ValueError:
                    pass
            return 0.0 # Return 0.0 if parsing fails or price is '-'

        stacjonarnie_price = parse_price(stacjonarnie_price_str_raw)
        chmura_price = parse_price(chmura_price_str_raw)

        products[product_name] = {
            "stacjonarnie": stacjonarnie_price,
            "chmura": chmura_price
        }
    return products

def load_product_data():
    return {
        "optima": parse_cennik_md('cennik-optima-firmy.md'),
        "xt": {"Faktury + Magazyn + Księga Podatkowa i Ryczałt": 1166.0} # Simplified for v3
    }

# --- Revenue Calculation Functions ---

def get_optima_discount(total_annual_sales):
    for tier in OPTIMA_DISCOUNT_TIERS["software"]:
        if tier["min_sales"] <= total_annual_sales <= tier["max_sales"]:
            software_commission = tier["discount"]
            upgrade_commission = software_commission - OPTIMA_DISCOUNT_TIERS["upgrade_offset"]
            return software_commission, upgrade_commission
    return 0, 0

def calculate_optima_revenue(optima_clients, all_products, current_year):
    cloud_recurring_commission = 0
    on_premise_purchase_commission = 0
    optima_upgrade_commission = 0

    # Simplified: Optima Cloud commission is fixed at 20% for all years.
    # The rabaty.md indicates tiered commissions based on total cloud sales, which is not implemented here.
    OPTIMA_CLOUD_COMMISSION_RATE = 0.20

    for client in optima_clients:
        if client["client_type"] == "stacjonarnie":
            # Simplified: On-premise commission tier is determined by individual client's initial value,
            # not the partner's cumulative sales volume over four quarters as per rabaty.md.
            software_commission_rate, upgrade_commission_rate = get_optima_discount(client["initial_value"])

            if current_year == client["acquisition_year"]:
                on_premise_purchase_commission += client["initial_value"] * software_commission_rate
            else:
                optima_upgrade_commission += client["initial_value"] * upgrade_commission_rate
        elif client["client_type"] == "chmura":
            # Monthly subscription for cloud clients, multiplied by 12
            monthly_cost = sum(all_products["optima"].get(m, {"chmura": 0})["chmura"] for m in client["modules"])
            cloud_recurring_commission += (monthly_cost * 12) * OPTIMA_CLOUD_COMMISSION_RATE
    return {
        "cloud_recurring_commission": cloud_recurring_commission,
        "on_premise_purchase_commission": on_premise_purchase_commission,
        "optima_upgrade_commission": optima_upgrade_commission,
        "total_commission": cloud_recurring_commission + on_premise_purchase_commission + optima_upgrade_commission,
        "details": {}
    }

def calculate_xt_revenue(year, all_products, num_xt_clients):
    price_per_client = all_products["xt"]["Faktury + Magazyn + Księga Podatkowa i Ryczałt"]

    if year == 1:
        commission_rate = XT_COMMISSION["year_1"]
    else:
        commission_rate = XT_COMMISSION["year_2_plus"]

    total_revenue = price_per_client * commission_rate * num_xt_clients

    return {
        "total_revenue": total_revenue,
        "details": {
            "price_per_client": price_per_client,
            "commission_rate": commission_rate,
            "num_xt_clients": num_xt_clients
        }
    }

# --- Phase 2 & 3: Core Simulation Logic ---

def print_initial_settings(all_products):
    print("--- Initial Simulation Settings ---")
    print(f"Simulation Length: {SIMULATION_YEARS} years")
    print(f"KSeF Year New Clients: {KSEF_YEAR_NEW_CLIENTS}")
    print(f"Annual Client Growth Rate: {ANNUAL_GROWTH_RATE:.0%}")
    print(f"On-Premise (Optima) Preference: {OPTIMA_PREFERENCE:.0%}")
    print("\n--- Defined Optima Packages by Company Size ---")

    for name, details in OPTIMA_PACKAGES_BY_SIZE.items():
        package_cost = sum(all_products["optima"].get(m, {}).get("stacjonarnie", 0) for m in details["modules"])
        print(f"  - {name}:")
        print(f"    - Retail Price (Stacjonarnie): {package_cost:,.2f} zł")
        print(f"    - Acquisition Probability: {details['probability']:.0%}")
        # print(f"    - Modules: {', '.join(details['modules'])}") # Optional: for more detail

def run_simulation():
    all_products = load_product_data()
    print_initial_settings(all_products)
    simulation_results = []

    # State tracking
    total_xt_clients = 0 # This will now be a cumulative count
    total_optima_clients = 0 # Cumulative count of all Optima clients
    total_optima_cloud_clients = 0 # Cumulative count of Optima cloud clients
    optima_clients_data = [] # To store details of each Optima client

    print("--- Running Multi-Year Growth Simulation ---")

    for year in range(1, SIMULATION_YEARS + 1):
        # 1. Customer Acquisition
        if year == 1:
            new_clients_total = KSEF_YEAR_NEW_CLIENTS
        else:
            new_clients_total = round((year - 1) * (KSEF_YEAR_NEW_CLIENTS * ANNUAL_GROWTH_RATE))

        # 2. Split clients between On-Premise (Optima) and Cloud (XT)
        new_optima_clients = round(new_clients_total * OPTIMA_PREFERENCE)
        new_xt_clients = new_clients_total - new_optima_clients

        # 3. Assign packages and client type to new Optima clients
        new_optima_clients_this_year = []
        new_optima_cloud_clients_this_year = 0 # This is for new cloud clients this year
        new_optima_package_breakdown = {pkg: {"stacjonarnie": 0, "chmura": 0} for pkg in OPTIMA_PACKAGES_BY_SIZE.keys()}

        for _ in range(new_optima_clients):
            r_pkg = random.random()
            cumulative_prob_pkg = 0
            chosen_package = None
            for pkg_name, pkg_details in OPTIMA_PACKAGES_BY_SIZE.items():
                cumulative_prob_pkg += pkg_details["probability"]
                if r_pkg < cumulative_prob_pkg:
                    chosen_package = pkg_name # Store name for breakdown
                    break

            if chosen_package:
                r_type = random.random()
                client_type = "stacjonarnie" if r_type < ON_PREMISE_VS_CLOUD_PREFERENCE else "chmura"

                new_optima_package_breakdown[chosen_package][client_type] += 1

                if client_type == "chmura":
                    new_optima_cloud_clients_this_year += 1

                initial_value = 0
                if client_type == "stacjonarnie":
                    # Sum of one-time purchase prices for modules
                    initial_value = sum(all_products["optima"].get(m, {}).get("stacjonarnie", 0) for m in OPTIMA_PACKAGES_BY_SIZE[chosen_package]["modules"])
                else:
                    # Sum of monthly cloud prices for modules (will be multiplied by 12 in revenue calc)
                    initial_value = sum(all_products["optima"].get(m, {}).get("chmura", 0) for m in OPTIMA_PACKAGES_BY_SIZE[chosen_package]["modules"])

                new_optima_clients_this_year.append({
                    "client_type": client_type,
                    "modules": OPTIMA_PACKAGES_BY_SIZE[chosen_package]["modules"],
                    "initial_value": initial_value,
                    "acquisition_year": year # Add acquisition year
                })

        optima_clients_data.extend(new_optima_clients_this_year)
        total_optima_clients += new_optima_clients # Update cumulative Optima clients
        total_optima_cloud_clients += new_optima_cloud_clients_this_year # Update cumulative Optima cloud clients

        # 4. Calculate Revenue for the year
        optima_rev = calculate_optima_revenue(optima_clients_data, all_products, year)

        # Update cumulative XT clients
        total_xt_clients += new_xt_clients

        if total_xt_clients > 0:
            xt_rev = calculate_xt_revenue(year, all_products, total_xt_clients)
        else:
            xt_rev = {"total_revenue": 0, "details": {}}

        # 6. Store results
        simulation_results.append({
            "year": year,
            "new_clients_total": new_clients_total,
            "new_optima_clients": new_optima_clients, # This is new Optima clients this year
            "total_optima_clients": total_optima_clients, # This is cumulative Optima clients
            "new_optima_cloud_clients": new_optima_cloud_clients_this_year, # New cloud clients this year
            "total_optima_cloud_clients": total_optima_cloud_clients, # Cumulative cloud clients
            "new_optima_package_breakdown": new_optima_package_breakdown,
            "new_xt_clients": new_xt_clients,
            "total_xt_clients": total_xt_clients,
            "optima_cloud_recurring_commission": optima_rev["cloud_recurring_commission"],
            "optima_on_premise_purchase_commission": optima_rev["on_premise_purchase_commission"],
            "optima_upgrade_commission": optima_rev["optima_upgrade_commission"],
            "xt_revenue": xt_rev["total_revenue"],
            "total_revenue": optima_rev["total_commission"] + xt_rev["total_revenue"]
        })

    return simulation_results

# --- Phase 4: Output and Refinement ---

def print_results(results):
    print("\n--- Simulation Results ---")
    header = f"| {'Year':<4} | {'New Clients':<12} | {'New Optima Clients':<18} | {'Total Optima Clients':<20} | {'Cumulative Optima Cloud Clients':<29} | {'Optima Pkg Breakdown':<22} | {'XT Clients':<10} | {'Total XT':<10} | {'Optima Cloud Comm (zł)':<22} | {'Optima On-Prem Comm (zł)':<24} | {'Optima Upgrade Comm (zł)':<26} | {'XT Comm (zł)':<15} | {'Total Comm (zł)':<18} |"
    print(header)
    print("-" * len(header))

    for res in results:
        pkg_breakdown_str = ", ".join([f"{counts['stacjonarnie']} {pkg_name} (On-Prem), {counts['chmura']} {pkg_name} (Cloud)" for pkg_name, counts in res["new_optima_package_breakdown"].items() if counts['stacjonarnie'] > 0 or counts['chmura'] > 0])
        print(f"| {res['year']:<4} | {res['new_clients_total']:<12} | {res['new_optima_clients']:<18} | {res['total_optima_clients']:<20} | {res['total_optima_cloud_clients']:<26} | {pkg_breakdown_str:<22} | {res['new_xt_clients']:<10} | {res['total_xt_clients']:<10} | {res['optima_cloud_recurring_commission']:>22,.2f} | {res['optima_on_premise_purchase_commission']:>24,.2f} | {res['optima_upgrade_commission']:>26,.2f} | {res['xt_revenue']:>15,.2f} | {res['total_revenue']:>18,.2f} |")

    print("-" * len(header))

    # Print summary
    final_year = results[-1]
    print("\n--- 5-Year Projection Summary ---")
    print(f"Total Clients Acquired: {sum(r['new_clients_total'] for r in results)}")
    print(f"Total Revenue Generated: {sum(r['total_revenue'] for r in results):,.2f} zł")
    print(f"Projected Annual Revenue in last year: {final_year['total_revenue']:,.2f} zł")

def export_results_to_csv(results, filename="simulation_results.csv"):
    import csv

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'Year', 'New Clients', 'New Optima Clients', 'Total Optima Clients',
            'Cumulative Optima Cloud Clients', 'Optima Pkg Breakdown', 'XT Clients', 'Total XT',
            'Optima Cloud Comm (zł)', 'Optima On-Prem Comm (zł)', 'Optima Upgrade Comm (zł)', 'XT Comm (zł)', 'Total Comm (zł)'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for res in results:
            pkg_breakdown_str = ", ".join([f"{counts['stacjonarnie']} {pkg_name} (On-Prem), {counts['chmura']} {pkg_name} (Cloud)" for pkg_name, counts in res["new_optima_package_breakdown"].items() if counts['stacjonarnie'] > 0 or counts['chmura'] > 0])
            writer.writerow({
                'Year': res['year'],
                'New Clients': res['new_clients_total'],
                'New Optima Clients': res['new_optima_clients'],
                'Total Optima Clients': res['total_optima_clients'],
                'Cumulative Optima Cloud Clients': res['total_optima_cloud_clients'],
                'Optima Pkg Breakdown': pkg_breakdown_str,
                'XT Clients': res['new_xt_clients'],
                'Total XT': res['total_xt_clients'],
                'Optima Cloud Comm (zł)': res['optima_cloud_recurring_commission'],
                'Optima On-Prem Comm (zł)': res['optima_on_premise_purchase_commission'],
                'Optima Upgrade Comm (zł)': res['optima_upgrade_commission'],
                'XT Comm (zł)': res['xt_revenue'],
                'Total Comm (zł)': res['total_revenue']
            })


    print(f"\nSimulation results exported to {filename}")


if __name__ == "__main__":
    # Ensure package probabilities sum to 1.0
    if sum(p['probability'] for p in OPTIMA_PACKAGES_BY_SIZE.values()) != 1.0:
        raise ValueError("Optima package probabilities must sum to 1.0")

    results = run_simulation()
    print_results(results)
    export_results_to_csv(results)
