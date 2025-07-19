import sys
import re
import random
import json

# --- Phase 1: Setup and Configuration ---

# Core Simulation Parameters
SIMULATION_YEARS = 8
KSEF_YEAR_NEW_CLIENTS = 1  # Aggressive target for the first year
ANNUAL_GROWTH_RATE = 0.20  # 20% increase in new client acquisition each year after Y1
ON_PREMISE_PREFERENCE = 1.00 # 80% of new clients choose on-premise (Optima)

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
OPTIMA_PACKAGES = {
    "Pakiet Start": {
        "modules": ["Faktury", "Księga Podatkowa", "CRM"],
        "probability": 0.40 # 40% of clients choose this
    },
    "Pakiet Handel": {
        "modules": ["Handel Plus", "Księga Handlowa Plus", "CRM Plus", "Analizy Business Intelligence"],
        "probability": 0.35 # 35% of clients choose this
    },
    "Pakiet Produkcja": {
        "modules": ["Handel Plus", "Księga Handlowa Plus", "Płace i Kadry Plus", "Serwis", "Obieg Dokumentów"],
        "probability": 0.25 # 25% of clients choose this
    }
}

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
        price_str_raw = cells[1]

        match = re.search(r'([\d\s,]+)', price_str_raw)
        price_str = ''
        if match:
            price_str = match.group(1).strip().replace(' ', '').replace(',', '.')
            if price_str.count('.') > 1:
                price_str = price_str.replace('.', '', price_str.count('.') - 1)
            try:
                products[product_name] = float(price_str)
            except ValueError:
                pass # Ignore parsing errors for this version
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
            return tier["discount"]
    return 0

def calculate_optima_revenue(products_sold, all_products):
    total_retail_value = sum(all_products["optima"].get(p, 0) * q for p, q in products_sold.items())
    discount = get_optima_discount(total_retail_value)
    partner_revenue = total_retail_value * discount
    return {
        "total_revenue": partner_revenue,
        "details": {
            "retail_value": total_retail_value,
            "discount_rate": discount,
        }
    }

def calculate_xt_revenue(year, all_products):
    price_per_client = all_products["xt"]["Faktury + Magazyn + Księga Podatkowa i Ryczałt"]

    if year == 1:
        commission_rate = XT_COMMISSION["year_1"]
    else:
        commission_rate = XT_COMMISSION["year_2_plus"]

    total_revenue = price_per_client * commission_rate

    return {
        "total_revenue": total_revenue,
        "details": {
            "price_per_client": price_per_client,
            "commission_rate": commission_rate
        }
    }

# --- Phase 2 & 3: Core Simulation Logic ---

def print_initial_settings(all_products):
    print("--- Initial Simulation Settings ---")
    print(f"Simulation Length: {SIMULATION_YEARS} years")
    print(f"KSeF Year New Clients: {KSEF_YEAR_NEW_CLIENTS}")
    print(f"Annual Client Growth Rate: {ANNUAL_GROWTH_RATE:.0%}")
    print(f"On-Premise (Optima) Preference: {ON_PREMISE_PREFERENCE:.0%}")
    print("\n--- Defined Optima Packages ---")

    for name, details in OPTIMA_PACKAGES.items():
        package_cost = sum(all_products["optima"].get(m, 0) for m in details["modules"])
        print(f"  - {name}:")
        print(f"    - Retail Price: {package_cost:,.2f} zł")
        print(f"    - Acquisition Probability: {details['probability']:.0%}")
        # print(f"    - Modules: {', '.join(details['modules'])}") # Optional: for more detail

def run_simulation():
    all_products = load_product_data()
    print_initial_settings(all_products)
    simulation_results = []

    # State tracking
    total_xt_clients = 0

    print("--- Running Multi-Year Growth Simulation ---")

    for year in range(1, SIMULATION_YEARS + 1):
        # 1. Customer Acquisition
        if year == 1:
            new_clients_total = KSEF_YEAR_NEW_CLIENTS
        else:
            last_year_new_clients = simulation_results[-1]["new_clients_total"]
            new_clients_total = round(last_year_new_clients * (1 + ANNUAL_GROWTH_RATE))

        # 2. Split clients between On-Premise (Optima) and Cloud (XT)
        new_optima_clients = round(new_clients_total * ON_PREMISE_PREFERENCE)
        new_xt_clients = new_clients_total - new_optima_clients

        # 3. Assign packages to new Optima clients
        optima_products_sold_this_year = {}
        for _ in range(new_optima_clients):
            r = random.random()
            cumulative_prob = 0
            for pkg_name, pkg_details in OPTIMA_PACKAGES.items():
                cumulative_prob += pkg_details["probability"]
                if r < cumulative_prob:
                    for module in pkg_details["modules"]:
                        optima_products_sold_this_year[module] = optima_products_sold_this_year.get(module, 0) + 1
                    break

        # 4. Calculate Revenue for the year
        optima_rev = calculate_optima_revenue(optima_products_sold_this_year, all_products)

        if new_xt_clients > 0:
            xt_rev = calculate_xt_revenue(year, all_products)
        else:
            xt_rev = {"total_revenue": 0, "details": {}}

        # 5. Update state for next year
        total_xt_clients = 1 if new_xt_clients > 0 else 0 # Cap at 1 if there's an XT client

        # 6. Store results
        simulation_results.append({
            "year": year,
            "new_clients_total": new_clients_total,
            "new_optima_clients": new_optima_clients,
            "new_xt_clients": new_xt_clients,
            "total_xt_clients": total_xt_clients,
            "optima_revenue": optima_rev["total_revenue"],
            "xt_revenue": xt_rev["total_revenue"],
            "total_revenue": optima_rev["total_revenue"] + xt_rev["total_revenue"]
        })

    return simulation_results

# --- Phase 4: Output and Refinement ---

def print_results(results):
    print("\n--- Simulation Results ---")
    header = f"| {'Year':<4} | {'New Clients':<12} | {'Optima Clients':<14} | {'XT Clients':<10} | {'Total XT':<10} | {'Optima Rev (zł)':<18} | {'XT Rev (zł)':<15} | {'Total Rev (zł)':<18} |"
    print(header)
    print("-" * len(header))

    for res in results:
        print(f"| {res['year']:<4} | {res['new_clients_total']:<12} | {res['new_optima_clients']:<14} | {res['new_xt_clients']:<10} | {res['total_xt_clients']:<10} | {res['optima_revenue']:>18,.2f} | {res['xt_revenue']:>15,.2f} | {res['total_revenue']:>18,.2f} |")

    print("-" * len(header))

    # Print summary
    final_year = results[-1]
    print("\n--- 5-Year Projection Summary ---")
    print(f"Total Clients Acquired: {sum(r['new_clients_total'] for r in results)}")
    print(f"Total Revenue Generated: {sum(r['total_revenue'] for r in results):,.2f} zł")
    print(f"Projected Annual Revenue in last year: {final_year['total_revenue']:,.2f} zł")


if __name__ == "__main__":
    # Ensure package probabilities sum to 1.0
    if sum(p['probability'] for p in OPTIMA_PACKAGES.values()) != 1.0:
        raise ValueError("Optima package probabilities must sum to 1.0")

    results = run_simulation()
    print_results(results)
