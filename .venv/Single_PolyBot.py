from dotenv import load_dotenv
import os
import requests
import json
import time
from datetime import datetime, date
import statistics
# Console text upgrades
bold_green = '\033[1;32m'
bold = '\033[1m'
reset = '\033[0m'

# Program start
load_dotenv()
alerts_webhook = os.getenv("ALERTS_WEBHOOK")
daily_recap_webhook = os.getenv("DAILY_RECAPS_WEBHOOK")

# Input slug
SLUG = ("will-gamestop-acquire-ebay")

# Input target question if needed
TARGET_QUESTION = None

# Input held position side
POSITION_SIDE = "no"

# Input buy price
BUY_PRICE = 0.85

# Input sell target
SELL_TARGET = 0.98

# Stop-loss threshold
stop_loss_threshold = round((BUY_PRICE  * 0.25), 2)
print(f"The stop-loss threshold is set to {stop_loss_threshold}")

# Discord functions
def send_alert(message):
    data = {"content": message}
    requests.post(alerts_webhook, json=data)
    print("Sent Alert")
def send_market_summary(message):
    data = {"content": message}
    requests.post(daily_recap_webhook, json=data)
    print("Sent Market Summary")

def get_holder_profit(holders):
    holders_dict = []
    # Fetch each holders all-time PNL from the PNL API
    for holder in holders:
        proxy_wallet = holder["proxyWallet"]
        name = holder["name"]
        holders_profit_url = f"https://user-pnl-api.polymarket.com/user-pnl?user_address={proxy_wallet}&interval=1m&fidelity=1d"
        holder_profit_data = (safety_net(holders_profit_url))

        if not holder_profit_data:
            continue

        last_profit = holder_profit_data[-1]["p"]
        holders_dict.append({"Name": name, "PNL": last_profit, "ProxyWallet": proxy_wallet})
    return holders_dict

def daily_recap():
    daily_recap_message = (
        f"🔊 --- DAILY RECAP | [{SLUG.replace('-', ' ').title()}: {TARGET_QUESTION}] ---"
    )
    send_market_summary(daily_recap_message)

    # Median PNL for yes/no holders
    ten_yes_median = round(statistics.median([h["PNL"] for h in yes_holders_data]))
    ten_no_median = round(statistics.median([h["PNL"] for h in no_holders_data]))
    # Text for top 3 yes/no holders
    y_top3_text = "\n".join([f"▫    {h['Name']}: ${h['PNL']:,.0f}" for h in yes_holders_data[:3]])
    n_top3_text = "\n".join([f"▫    {h['Name']}: ${h['PNL']:,.0f}" for h in no_holders_data[:3]])
    holders_message = (
        f"💵Top 10 Yes holders median PNL: ${ten_yes_median:,.0f}\n🥉Top 3 Yes holders PNL: \n{y_top3_text}\n\n💵Top 10 No holders median PNL: ${ten_no_median:,.0f}\n🥉Top 3 No holders PNL: \n{n_top3_text}"
    )
    send_market_summary(holders_message)

COOLDOWN_TIME = 300
def check_holder_moves():
    pending_moves = {}
    last_checked = {}
    top_5_holders = yes_holders_data[:5] + no_holders_data[:5]
    now = time.time()

    for holder in top_5_holders:
        wallet = holder["ProxyWallet"]
        name = holder["Name"]
        actvity_url = (
            f"https://data-api.polymarket.com/activity?user={wallet}&market={condition_id}&type=TRADE&start=1700000000&sortDirection=ASC"
        )
        holder_trades = (safety_net(actvity_url))

        if not holder_trades:
            continue

        for trade in holder_trades:
            if wallet not in pending_moves:
                pending_moves[wallet] = {
                    "Name": name,
                    "Side": trade["side"],
                    "Outcome": trade["outcome"],
                    "Price": trade["price"],
                    "Size": 0,
                    "usdcSize": 0,
                    "Timestamp": 0,
                }



            if trade["side"] != pending_moves[wallet]["Side"] or trade["outcome"] != pending_moves[wallet]["Outcome"]:
                flush_moves()
            if now - pending_moves[wallet]["Timestamp"] >= COOLDOWN_TIME:
                flush_moves()

            pending_moves[wallet]["usdcSize"] += trade["usdcSize"]
            pending_moves[wallet]["Size"] += trade["size"]
            pending_moves[wallet]["Timestamp"] = trade["timestamp"]
            pending_moves[wallet]["Outcome"] = trade["outcome"]
            pending_moves[wallet]["Side"] = trade["side"]

            last_checked[wallet] = pending_moves[wallet]["Timestamp"]
            #print(last_checked)


        print(holder_trades)



    print(pending_moves)

def flush_moves():
    print("test")


def safety_net(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        api_fail_message = (f"🛑WARNING: API call failed for {url}: {e}")
        print(api_fail_message)
        send_alert(api_fail_message)
        return None

    except json.JSONDecodeError as e:
        json_fail_message = (f"🛑WARNING: Got a response but couldn't parse it as JSON for {url}: {e}")
        print(json_fail_message)
        send_alert(json_fail_message)
        return None

# Pull market data
url = f"https://gamma-api.polymarket.com/events?slug={SLUG}"
event_data = safety_net(url)
for market in event_data[0]["markets"]:
    if TARGET_QUESTION is None or TARGET_QUESTION in market["question"]:
        print(market)
        # Saving start data
        market_link = (f"https://polymarket.com/event/{SLUG}")
        condition_id = market["conditionId"]
        holders_url = f"https://data-api.polymarket.com/holders?market={condition_id}&limit=10&offset=0"
        end_date_raw = (market["endDate"])
        end_date = datetime.strptime(end_date_raw, "%Y-%m-%dT%H:%M:%SZ").date()
        resolution_status = ((market["umaResolutionStatuses"]).strip('[""]'))

        startup_message = f"⌚ --- STARTUP | Now watching [{SLUG.replace('-', ' ').title()}: {TARGET_QUESTION}] ---\n{market_link}\n"
        send_alert(startup_message)

        # Saving start prices
        outcomePrices_raw = (market["outcomePrices"])
        outcomePrices = json.loads(outcomePrices_raw)
        yes_price = outcomePrices[0]
        no_price = outcomePrices[1]
        daily_start_price = float(yes_price)

        # Skip if market has resolved
        if resolution_status != ("proposed") or resolution_status != ("disputed"):
            # Low liquidity/24hr volume warning
            liquidity_raw = (market["liquidity"])
            liquidity = (round(json.loads(liquidity_raw)))
            volume24hr_raw = (market["volume24hr"])
            volume24hr = (round(volume24hr_raw))
            print(f"liquidity: {liquidity}")
            print(f"volume24hr: {volume24hr}")

            if liquidity < 70000:
                send_alert(
                    f"⚠ WARNING: The liquidity is low (${liquidity}). Orderbook cannot absorb big orders without price moving.")
            if volume24hr < 15000:
                send_alert(
                    f"⚠ WARNING: The 24hr volume is low (${volume24hr}). Market might not reflect current sentiment.")

        price_alerted = []
        days_till_resolution_alerted = []
        resolution_status_alerted = []
        last_run_date = None
        sell_target_hit = False
        stop_loss_hit = False
        while True:
            event_data = (safety_net(url))
            # Tracking just target question only when needed
            for m in event_data[0]["markets"]:
                if TARGET_QUESTION is None or TARGET_QUESTION in m["question"]:
                    market = m

            # Repeated program start for loop
            outcomePrices_raw = (market["outcomePrices"])
            outcomePrices = json.loads(outcomePrices_raw)
            yes_price = float(outcomePrices[0])
            no_price = float(outcomePrices[1])
            current_price = float(yes_price)
            resolution_status = ((market["umaResolutionStatuses"]).strip('[""]'))
            holders_data = (safety_net(holders_url))
            yes_holders_data = get_holder_profit(holders_data[0]["holders"])
            no_holders_data = get_holder_profit(holders_data[1]["holders"])
            check_holder_moves()

            # Resolution status alert
            if (resolution_status == ("proposed") or resolution_status == ("disputed")) and (resolution_status not in resolution_status_alerted):
                resolution_status_message = (
                    f"🚨 ALERT: The market resolution has been {resolution_status}.\n{market_link}"
                )
                send_alert(resolution_status_message)
                resolution_status_alerted.append(resolution_status)

            # Sell target / Stop loss alerts
            if POSITION_SIDE == "no":
                if no_price >= SELL_TARGET and not sell_target_hit:
                    sell_target_message = (
                        f"🚨 ALERT: The No side has reached your sell target. Sell Target: {SELL_TARGET} | No Price: {no_price:.2f}\n{market_link}"
                    )
                    send_alert(sell_target_message)
                    sell_target_hit = True
                if no_price <= stop_loss_threshold and not stop_loss_hit:
                    stop_loss_message = (
                        f"🚨 ALERT: The No side has dropped to your stop loss threshold, SELL NOW. Stop Loss Threshold: {stop_loss_threshold} | No Price: {no_price:.2f}\n{market_link}"
                    )
                    send_alert(stop_loss_message)
                    stop_loss_hit = True

            elif POSITION_SIDE == "yes":
                if yes_price >= SELL_TARGET and not sell_target_hit:
                    sell_target_message = (
                        f"🚨 ALERT: The Yes side has reached your sell target. Sell Target: {SELL_TARGET} | Yes Price: {yes_price:.2f}\n{market_link}"
                    )
                    send_alert(sell_target_message)
                    sell_target_hit = True

                if yes_price <= stop_loss_threshold and not stop_loss_hit:
                    stop_loss_message = (
                        f"🚨 ALERT: The Yes side has dropped to your stop loss threshold SELL NOW: Stop Loss Treshold: {stop_loss_threshold} | Yes Price: {yes_price:.2f}\n{market_link}"
                    )
                    send_alert(stop_loss_message)
                    stop_loss_hit = True

            else:
                sell_target_message = (
                    f"🛑WARNING: Set your sell and stop-loss target inside the program"
                )
                send_alert(sell_target_message)

            # Tresholds to loop through
            thresholds = [0.01,0.025, 0.05, 0.10, 0.15, 0.20, 0.25]
            # Looping through given thresholds
            for threshold in thresholds:
                if threshold in price_alerted:
                    continue
                    # Checks for shift and sends alert
                if current_price <= (daily_start_price - threshold) or current_price >= (daily_start_price + threshold):
                    alert_message = (
                        f"🔊 ALERT: The price has shifted {threshold * 100}¢ since midnight.")
                    price_message = (
                        f"📊 The current prices are [Yes_price: {yes_price} | No_price: {no_price}]\n{market_link}")
                    price_alerted.append(threshold)
                    send_alert(alert_message)
                    send_alert(price_message)

            # Midnight recap call
            date_today = date.today()
            if date_today != last_run_date:
                daily_recap()
                # Midnight variables to reset
                alerted_thresholds = []
                last_run_date = date_today
                sell_target_hit = False
                stop_loss_hit = False
                daily_start_price = float(yes_price)

            # End date approaching warning
            days_remaining = (end_date - date_today).days
            if days_remaining in (7, 3, 1) and days_remaining not in days_till_resolution_alerted_alerted:
                resolution_days_message = (
                    f"⏳ ALERT: Market resolves in {days_remaining} days.\n{market_link}"
                )
                send_alert(resolution_days_message)
                days_till_resolution_alerted.append(days_remaining)
            time.sleep(60)