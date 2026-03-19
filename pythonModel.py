import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# --- PAGE CONFIG ---
st.set_page_config(page_title="Gordo Model Engine", layout="wide")

# --- CORE MATH ENGINE ---
def calculate_core_math(inputs):
    days_per_month = 30.4
    years_to_plot = 15
    months_to_plot = years_to_plot * 12
    
    # 1. Traffic & Fuel
    daily_cars = (inputs['aadt'] * inputs['capture_rate']) + inputs['local_cust']
    monthly_cars = daily_cars * days_per_month
    
    # Accounting for Fuel Conversion Rate
    monthly_gallons = (monthly_cars * inputs['fuel_conv_rate']) * inputs['fillup_gal']
    net_fuel_margin = inputs['base_margin'] - inputs['brand_penalty']
    monthly_fuel_profit = monthly_gallons * net_fuel_margin
    
    # 2. C-Store Inside
    monthly_inside_cust = monthly_cars * inputs['conv_rate']
    monthly_inside_rev = monthly_inside_cust * inputs['avg_ticket']
    # Royalty pulled from Gross Revenue
    monthly_inside_profit = (monthly_inside_rev * inputs['inside_margin']) - (monthly_inside_rev * inputs['royalty_pct'])
    
    # 3. Foodservice
    monthly_food_cust = monthly_inside_cust * inputs['food_conv_rate']
    monthly_food_rev = monthly_food_cust * inputs['avg_food_ticket']
    raw_food_cogs = monthly_food_rev * (1 - inputs['food_margin'])
    spoilage_cost = raw_food_cogs * inputs['spoilage_pct']
    monthly_food_profit = (monthly_food_rev * inputs['food_margin']) - spoilage_cost
    
    lost_inside_profit = (monthly_food_cust * inputs['cannibal_pct']) * inputs['avg_ticket'] * inputs['inside_margin']
    
    # 4. Point of Sale Friction
    monthly_cc_fees = (monthly_inside_rev + monthly_food_rev) * inputs['cc_fee_pct'] + ((monthly_inside_cust + monthly_food_cust) * 0.10)
    
    # 5. EBITDA
    total_monthly_income = monthly_fuel_profit + monthly_inside_profit + monthly_food_profit - lost_inside_profit - monthly_cc_fees
    total_monthly_opex = inputs['utilities'] + inputs['payroll'] + inputs['maint'] + inputs['overhead']
    monthly_ebitda = total_monthly_income - total_monthly_opex
    
    # 6. Debt Service (Amortization)
    loan_amount = inputs['total_cost'] * (1 - inputs['owner_equity_pct'])
    monthly_rate = inputs['interest_rate'] / 12
    
    if monthly_rate > 0 and inputs['loan_months'] > 0:
        monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**inputs['loan_months']) / ((1 + monthly_rate)**inputs['loan_months'] - 1)
    else:
        monthly_payment = loan_amount / max(inputs['loan_months'], 1)
    
    # 7. Month-over-Month Simulation
    loan_balance_trace = []
    pocket_cash_trace = []
    current_balance = loan_amount
    
    for m in range(1, months_to_plot + 1):
        if current_balance > 0:
            interest_charge = current_balance * monthly_rate
            standard_prin = monthly_payment - interest_charge
            
            # Accelerated Strategy
            if inputs['extra_pay_method'] == '% of Cash Flow':
                baseline_cf = monthly_ebitda - monthly_payment
                extra_prin = max(0, baseline_cf * (inputs['extra_pay_value'] / 100))
            else:
                extra_prin = inputs['extra_pay_value'] / 12
                
            total_prin = min(current_balance, standard_prin + extra_prin)
            current_balance -= total_prin
            
            # Pocket cash is EBITDA minus actual debt outflow
            monthly_pocket = monthly_ebitda - (interest_charge + total_prin)
        else:
            current_balance = 0
            monthly_pocket = monthly_ebitda
            
        loan_balance_trace.append(current_balance)
        pocket_cash_trace.append(monthly_pocket)
        
    return {
        "monthly_ebitda": monthly_ebitda,
        "monthly_payment": monthly_payment,
        "dscr": monthly_ebitda / monthly_payment if monthly_payment > 0 else 0,
        "loan_trace": loan_balance_trace,
        "cum_cash_trace": np.cumsum(pocket_cash_trace),
        "months": np.arange(1, months_to_plot + 1) / 12
    }

# --- UI LAYOUT ---
st.title("⛽ Gordo Fuel & Retail Model Engine")
st.markdown("---")

tab1, tab2 = st.tabs(["System Inputs", "Sweep Analysis"])

with tab1:
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Traffic & Fuel")
        aadt = st.number_input("AADT", value=8100)
        cap_rate = st.number_input("Hwy Capture Rate (dec)", value=0.035, format="%.3f")
        local_cust = st.number_input("Local Daily Customers", value=150)
        fuel_conv = st.number_input("Fuel Conv Rate (dec)", value=0.75)
        fillup = st.number_input("Avg Fill-up (gal)", value=15)
        margin = st.number_input("Base Fuel Margin ($)", value=0.27)
        penalty = st.number_input("Brand Penalty ($)", value=0.00)

    with col2:
        st.subheader("C-Store & Ops")
        conv_rate = st.number_input("Inside Conv Rate (dec)", value=0.80)
        avg_tkt = st.number_input("Avg Inside Ticket ($)", value=14.50)
        ins_margin = st.number_input("Inside Margin (dec)", value=0.35)
        royalty = st.number_input("Franchise Royalty (dec)", value=0.00)
        cc_fee = st.number_input("CC Swipe Fee (dec)", value=0.025, format="%.3f")
        
        st.subheader("Monthly OpEx")
        util = st.number_input("Utilities ($)", value=2800)
        payroll = st.number_input("Payroll ($)", value=16238)
        maint = st.number_input("Maint/Repair ($)", value=1200)
        fixed = st.number_input("Fixed Overhead ($)", value=3500)

    with col3:
        st.subheader("Food & Strategy")
        f_conv = st.number_input("Food Conv Rate (dec)", value=0.20)
        f_tkt = st.number_input("Avg Food Ticket ($)", value=7.50)
        f_margin = st.number_input("Food Margin (dec)", value=0.65)
        spoil = st.number_input("Spoilage Pct (dec)", value=0.05)
        cannibal = st.number_input("Cannibalization (dec)", value=0.10)
        
        st.subheader("Accelerated Payoff")
        strat_type = st.selectbox("Strategy Type", ["% of Cash Flow", "Fixed Amount ($/yr)"])
        strat_val = st.number_input("Strategy Value (% or $)", value=0)

    st.markdown("---")
    st.subheader("Financial Performance (Baseline)")
    
    # Loan Inputs for calculation
    cost = st.number_input("Total Project Cost ($)", value=2480000)
    equity = st.number_input("Owner Equity (dec)", value=0.20)
    interest = st.number_input("Loan Interest Rate (dec)", value=0.095, format="%.3f")
    term = st.number_input("Loan Term (months)", value=180)

    # Trigger Baseline Calculation
    base_in = {
        'aadt': aadt, 'capture_rate': cap_rate, 'local_cust': local_cust, 'fuel_conv_rate': fuel_conv,
        'fillup_gal': fillup, 'base_margin': margin, 'brand_penalty': penalty, 'conv_rate': conv_rate,
        'avg_ticket': avg_tkt, 'inside_margin': ins_margin, 'royalty_pct': royalty, 'cc_fee_pct': cc_fee,
        'food_conv_rate': f_conv, 'avg_food_ticket': f_tkt, 'food_margin': f_margin, 'spoilage_pct': spoil,
        'cannibal_pct': cannibal, 'total_cost': cost, 'owner_equity_pct': equity, 'utilities': util,
        'payroll': payroll, 'maint': maint, 'overhead': fixed, 'interest_rate': interest, 'loan_months': term,
        'extra_pay_method': strat_type, 'extra_pay_value': strat_val
    }
    
    res = calculate_core_math(base_in)
    
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Monthly EBITDA", f"${res['monthly_ebitda']:,.0f}")
    
    dscr_color = "normal" if res['dscr'] >= 1.25 else "inverse"
    m_col2.metric("Lender DSCR", f"{res['dscr']:.2f}", delta="Bank Threshold 1.25", delta_color=dscr_color)
    
    m_col3.metric("Est. Payoff", f"{np.min(res['months'][np.array(res['loan_trace']) <= 0]):.1f} Years" if any(np.array(res['loan_trace']) <= 0) else "15+ Years")

with tab2:
    st.subheader("Parametric Sweep Settings")
    
    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    sweep_key_map = {
        "AADT": "aadt", "Capture Rate": "capture_rate", "Fuel Margin": "base_margin",
        "Inside Conv": "conv_rate", "Payroll": "payroll", "Interest Rate": "interest_rate"
    }
    sweep_label = s_col1.selectbox("Variable to Sweep", list(sweep_key_map.keys()))
    s_min = s_col2.number_input("Min Value", value=float(base_in[sweep_key_map[sweep_label]]) * 0.7)
    s_max = s_col3.number_input("Max Value", value=float(base_in[sweep_key_map[sweep_label]]) * 1.3)
    s_steps = s_col4.slider("Steps", 2, 8, 4)
    
    sweep_vals = np.linspace(s_min, s_max, s_steps)
    
    fig_loan = go.Figure()
    fig_cash = go.Figure()
    
    for val in sweep_vals:
        sweep_in = base_in.copy()
        sweep_in[sweep_key_map[sweep_label]] = val
        s_res = calculate_core_math(sweep_in)
        
        lbl = f"{sweep_label}: {val:,.2f}"
        fig_loan.add_trace(go.Scatter(x=s_res['months'], y=s_res['loan_trace'], name=lbl, mode='lines'))
        fig_cash.add_trace(go.Scatter(x=s_res['months'], y=s_res['cum_cash_trace'], name=lbl, mode='lines'))

    fig_loan.update_layout(title="Loan Paydown Curves", xaxis_title="Years", yaxis_title="Debt Balance ($)", hovermode="x unified")
    fig_cash.update_layout(title="Cumulative Net Earnings (ROI Tracker)", xaxis_title="Years", yaxis_title="Total Cash ($)", hovermode="x unified")
    
    # Add Break-even reference line
    fig_cash.add_hline(y=(cost * equity), line_dash="dash", line_color="red", annotation_text="Initial Down Payment")
    
    st.plotly_chart(fig_loan, use_container_width=True)
    st.plotly_chart(fig_cash, use_container_width=True)
    # --- TAB 3: METHODOLOGY & EQUATIONS ---
with st.tabs(["System Inputs", "Sweep Analysis", "Methodology"])[2]:
    st.header("🧮 Model Physics & Mathematical Methodology")
    st.info("This model uses a month-over-month iterative simulation to account for debt amortization and accelerated principal payments.")

    # 1. Traffic & Revenue Equations
    st.subheader("1. Traffic & Fuel Volume")
    st.latex(r"Monthly\ Cars = \left( (AADT \times Capture\ Rate) + Local\ Customers \right) \times 30.4")
    st.latex(r"Monthly\ Gallons = (Monthly\ Cars \times Fuel\ Conv\ Rate) \times Avg\ Fillup")
    
    st.markdown("""
    > **Note:** We apply a *Fuel Conversion Rate* because not every vehicle that enters the 
    > premises (specifically for food or coffee) will utilize the fuel pumps.
    """)

    # 2. C-Store & Food Profitability
    st.subheader("2. Retail & Foodservice Profit")
    st.write("**Inside Retail Net Profit:**")
    st.latex(r"Profit_{Inside} = (Revenue_{Inside} \times Margin_{Inside}) - (Revenue_{Inside} \times Royalty_{Pct})")
    
    st.write("**Foodservice Net Profit (Accounting for Spoilage):**")
    st.latex(r"COGS_{Food} = Revenue_{Food} \times (1 - Margin_{Food})")
    st.latex(r"Profit_{Food} = (Revenue_{Food} \times Margin_{Food}) - (COGS_{Food} \times Spoilage_{Pct})")

    # 3. Friction & OpEx
    st.subheader("3. Friction Costs & EBITDA")
    st.latex(r"CC\ Fees = (Total\ Inside\ Revenue \times CC_{Pct}) + (Total\ Customers \times \$0.10)")
    st.latex(r"EBITDA = \sum(Profits) - \sum(OpEx) - CC\ Fees")

    # 4. Debt & DSCR
    st.subheader("4. Debt Service & Lender Requirements")
    st.write("**Monthly Loan Payment (Standard Amortization):**")
    st.latex(r"M = P \frac{r(1+r)^n}{(1+r)^n - 1}")
    st.markdown("""
    * $P$ = Principal (Total Cost - Owner Equity)
    * $r$ = Monthly Interest Rate (Annual Rate / 12)
    * $n$ = Total Months (Term)
    """)

    st.write("**Debt Service Coverage Ratio (DSCR):**")
    st.latex(r"DSCR = \frac{Monthly\ EBITDA}{Monthly\ Loan\ Payment}")
    st.success("A DSCR of **1.25** is the standard minimum threshold for commercial lending approval.")

    # 5. Cumulative Wealth
    st.subheader("5. Cumulative Net Earnings")
    st.latex(r"Cumulative\ Cash_m = \sum_{i=1}^{m} (EBITDA_i - Total\ Debt\ Outflow_i)")
    st.write("Where *Total Debt Outflow* includes interest, standard principal, and any accelerated principal payments.")