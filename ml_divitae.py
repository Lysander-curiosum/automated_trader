import os
import asyncio
import alpaca_trade_api as tradeapi
import pandas as pd
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from pytz import timezone
import numpy as np
import numpy as np  
import matplotlib.pyplot as plt  
import seaborn as seabornInstance 
from sklearn.model_selection import train_test_split 
from sklearn.linear_model import LinearRegression
from sklearn import metrics
%matplotlib inline

#Ok. Here is the experimental side of the bot. Might not be ready for this stage
# yet, because there are still obviously some kinks in the code 
# but, you can begin to upload the ml libraries and such to start trying to implement
# simple algo's in the selction process 

# (i.e how to gather the data for the potential symbols in between initial seach and purchase/sell)



min_share_price = 2.0
max_share_price = 10.0

min_last_dv = 500000

# Stop limit to default to (How much of the purchase price we want to sell at)
default_stop = .95

# How much of our portfolio to allocate to any one position
#I would say ten percent (this is considering my whopping 50 dollar portfolio. Testing this first with paper trading)
risk = 0.1

#maybe a solution? streaming connection formulated with different base_url? We will see. Fuck I want to move onto the trading stuff itself
base_url = 'https://paper-api.alpaca.markets'
api_key_id = 'PK9ARLC4LDLBUIM8BYYD'
api_secret = 'Qo8LXpc2PjWpOROe10WFmYu7VN4b3itn5Q6pIZYC'

api = tradeapi.REST(
    base_url=base_url,
    key_id=api_key_id,
    secret_key=api_secret
)

#api = tradeapi.REST('PKH4GJDOEPBOL3WUKHZU', 'r1JjbxeAeoO88pGMyXP0uJxQ1F6QYKSO0hk2wLNM', 'https://paper-api.alpaca.markets', api_version='v2') 
account = api.get_account()


#email notifications, if executing with the google cloud function, would be interesting. Perhaps hold off on
#implementation for now, would have to look over bruh.py to get an idea of functionality 
#in other words, ignore this for now 



# pretty easy to implement email notifications 
# this would be so easy to use in an app (in terms of allowing users to set up their own bot 
# with these specifications )
# lets run this as a google cloud function, and see if it executes (hooray, I can't believe we've made it work and you 
# understand it somewhat)
sender_address = 'slashpowben@gmail.com'
sender_pass = 'fivecrystals'
receiver_address = 'biirving30@gmail.com'
#Setup the MIME
message = MIMEMultipart()
message['From'] = 'Trading Bot'
message['To'] = receiver_address
message['Subject'] = 'The algorithm of your creation.'   #The subject line

def get_1000m_history_data(symbols):
    # this should execute at the very least
    print('Getting historical data...')
    minute_history = {}
    c = 0
    for symbol in symbols:
    	#historic_agg isn't supported, so you have to problem shoot that 
        #find the python polygon documentation! or the alpaca one. why are they so hard to find?
        # maybe this is get_agg and not get_barset? But on the errors found from other users, this doesn't
        # appear to be the case (I don't know, figure it out) Hella irritating
        minute_history[symbol] = api.polygon.aggregate(
            symbol, 'minute', limit=1000
        ).df
        c += 1
        print('{}/{}'.format(c, len(symbols)))
    print('Success.')
    return minute_history

#this funciton allows me to grab all of the stocks within a certain range (in a bot creation page
# these could be user input) <-- would be relatively easy to implement I think

def get_tickers():
    print('Getting current ticker data...')
    tickers = api.polygon.all_tickers()
    print('Success.')
    assets = api.list_assets()
    symbols = [asset.symbol for asset in assets if asset.tradable]
    # this is where you can tinker with specifications. Search farther along to find where further weeding out occurs in selection process.

    return [ticker for ticker in tickers if (
        ticker.ticker in symbols and
        ticker.lastTrade['p'] >= min_share_price and
        ticker.lastTrade['p'] <= max_share_price and
        ticker.prevDay['v'] * ticker.lastTrade['p'] > min_last_dv and
        ticker.todaysChangePerc >= 3.5 
        #I believe that it would in this segment that we would implement linear regression, simple (perhaps if previous day's predicted price less than actual? Exponential increase?)

#using farther reaching data gathering? data from the last week instead of just the previous day?
    )]

def find_stop(current_value, minute_history, now):
    series = minute_history['low'][-100:] \
                .dropna().resample('5min').min()
    series = series[now.floor('1D'):]
    diff = np.diff(series.values)
    low_index = np.where((diff[:-1] <= 0) & (diff[1:] > 0))[0] + 1
    if len(low_index) > 0:
        return series[low_index[-1]] - 0.01
    return current_value * default_stop


print("This works?! Don't get ahead of yourself. Last deployment, this function failed on the cloud function platform.")

#Okay. Try to understand this function, before moving on. See if you can find code section where trade executes. 

def run(tickers, market_open_dt, market_close_dt):

   # Establish streaming connection
   # specify data stream????? You need to change this line of code, to specify specific thingy? I don't know this shit is 
   # annoying
   #find the right data stream to establish the connection with

   #to make any progress forward, you need to find an alternative data stream anywhere pls jesus why are there so many hurdles
   #also not quite sure about the data_url will look back at this later
   #okay fuck you bruh this still doesn't work
    conn = tradeapi.StreamConn(key_id=api_key_id, secret_key=api_secret, base_url=base_url)


   # conn = tradeapi.StreamConn('PKH4GJDOEPBOL3WUKHZU', 'r1JjbxeAeoO88pGMyXP0uJxQ1F6QYKSO0hk2wLNM')

    #to make live changes? We'll see

    # Update initial state with information from tickers
    volume_today = {}
    prev_closes = {}
    for ticker in tickers:
        symbol = ticker.ticker
        prev_closes[symbol] = ticker.prevDay['c']
        volume_today[symbol] = ticker.day['v']

    symbols = [ticker.ticker for ticker in tickers]
    print('Tracking {} symbols.'.format(len(symbols)))

    minute_history = get_1000m_history_data(symbols)

    # no this is where function stops. (doesn't seem to print portfolio value)
    portfolio_value = float(api.get_account().portfolio_value)

    open_orders = {}
    positions = {}

    # Cancel any existing open orders on watched symbols
    existing_orders = api.list_orders(limit=500)
    for order in existing_orders:
        if order.symbol in symbols:
            api.cancel_order(order.id)

    stop_prices = {}
    latest_cost_basis = {}

    # Track any positions bought during previous executions
    existing_positions = api.list_positions()
    for position in existing_positions:
        if position.symbol in symbols:
            positions[position.symbol] = float(position.qty)
            # Recalculate cost basis and stop price
            # cost_basis is just the original price of the asset, pre-tax/dividend and other stuff

            latest_cost_basis[position.symbol] = float(position.cost_basis)
            stop_prices[position.symbol] = (
                float(position.cost_basis) * default_stop
            )

    # Keep track of what we're buying/selling
    target_prices = {}
    partial_fills = {}

    # Use trade updates to keep track of our portfolio
    @conn.on(r'trade_updates')
    async def handle_trade_update(conn, channel, data):
        symbol = data.order['symbol']
        last_order = open_orders.get(symbol)

        if last_order is not None:
            event = data.event
            if event == 'partial_fill':
                qty = int(data.order['filled_qty'])
                if data.order['side'] == 'sell':
                    qty = qty * -1
                positions[symbol] = (
                    # what is the purpose of the 0 in the code???!!
                    positions.get(symbol, 0) - partial_fills.get(symbol, 0)
                )

                partial_fills[symbol] = qty

                positions[symbol] += qty

                open_orders[symbol] = data.order

            elif event == 'fill':
                qty = int(data.order['filled_qty'])
                if data.order['side'] == 'sell':
                    qty = qty * -1
                positions[symbol] = (
                    positions.get(symbol, 0) - partial_fills.get(symbol, 0)
                )
                partial_fills[symbol] = 0
                positions[symbol] += qty
                open_orders[symbol] = None
            elif event == 'canceled' or event == 'rejected':
                partial_fills[symbol] = 0
                open_orders[symbol] = None

    @conn.on(r'A$')
    async def handle_second_bar(conn, channel, data):
        symbol = data.symbol

        # First, aggregate 1s bars for up-to-date MACD calculations
        # Exponential moving weighted average (12 day ema - 26 day ema)
        # puts more weight on the recent price adjustments (effective moreso than the SMA, because recent development
        # has more bearing over the effectiveness of the algo as a whole)

        ts = data.start
        ts -= timedelta(seconds=ts.second, microseconds=ts.microsecond)
        try:
            current = minute_history[data.symbol].loc[ts]
        except KeyError:
            current = None
        new_data = []
        if current is None:
            new_data = [
                data.open,
                data.high,
                data.low,
                data.close,
                data.volume
            ]
        else:
            new_data = [
                current.open,
                data.high if data.high > current.high else current.high,
                data.low if data.low < current.low else current.low,
                data.close,
                current.volume + data.volume
            ]
        minute_history[symbol].loc[ts] = new_data

        # Next, check for existing orders for the stock
        existing_order = open_orders.get(symbol)
        if existing_order is not None:
            # Make sure the order's not too old
            submission_ts = existing_order.submitted_at.astimezone(
                timezone('America/New_York')
            )
            order_lifetime = ts - submission_ts
            if order_lifetime.seconds // 60 > 1:
                # Cancel it so we can try again for a fill
                api.cancel_order(existing_order.id)
            return

        # Now we check to see if it might be time to buy or sell
        since_market_open = ts - market_open_dt
        until_market_close = market_close_dt - ts
        if (
            since_market_open.seconds // 60 > 15 and
            since_market_open.seconds // 60 < 60
        ):
            # Check for buy signals

            # See if we've already bought in first
            position = positions.get(symbol, 0)
            if position > 0:
                return

            # See how high the price went during the first 15 minutes
            lbound = market_open_dt
            ubound = lbound + timedelta(minutes=15)
            high_15m = 0
            try:
                high_15m = minute_history[symbol][lbound:ubound]['high'].max()
            except Exception as e:
                # Because we're aggregating on the fly, sometimes the datetime
                # index can get messy until it's healed by the minute bars
                return

            # Get the change since yesterday's market close

            daily_pct_change = (
                (data.close - prev_closes[symbol]) / prev_closes[symbol]
            )
            if (
                daily_pct_change > .04 and
                data.close > high_15m and
                volume_today[symbol] > 30000
            ):
                # check for a positive, increasing MACD
                hist = macd(
                    minute_history[symbol]['close'].dropna(),
                    n_fast=12,
                    n_slow=26
                )
                if (
                    hist[-1] < 0 or
                    not (hist[-3] < hist[-2] < hist[-1])
                ):
                    return
                hist = macd(
                    minute_history[symbol]['close'].dropna(),
                    n_fast=40,
                    n_slow=60
                )
                if hist[-1] < 0 or np.diff(hist)[-1] < 0:
                    return


                #This is the segment in which we should use linear regression, to gether the last (month?) of closing values for the stock,
                # spit out prediction and compare with current price 

# store closing prices from last week into an array 
# run through the linear regression (python code from example)
# then, try to store output number in separate variable, and compare it to most recent closing price 
# if predicted higher than current, purchase. If not, don't 
# Think more deeply about this output and what it means

                #multivariable, or simply closing price? Let'a start with closing price
             
    

                # does this store the last 100 values, though? I am not sure. 



                Y = []

               


                # The flaw is that one has to reenter thec current date, editing the cloud function with 
                # each iteration 
                # get current date?
                Y[symbol] = api.polygon.HistoricNBboQuotesV2ApiResponse(
                        symbol, date=date.today(), limit=1000
                    )
                print('Success. Of a sort. Perhaps')
                

                # independent variable? In this case, would it be dates vs. stock price

                
                # Do you just return the last 100 days? How would this work?
                
                X = []  # what you want to predict (independent variable)
                for x in range 100:
                     X.insert(x, x)

                model = LinearRegression()
                model.fit(X, y)

                X_predict = []  
                y_predict = model.predict(X_predict) # for which y values 

                

                # Stock has passed all checks; figure out how much to buy
                stop_price = find_stop(
                    data.close, minute_history[symbol], ts
                )
                stop_prices[symbol] = stop_price
                target_prices[symbol] = data.close + (
                    (data.close - stop_price) * 3
                )
                shares_to_buy = portfolio_value * risk // (
                    data.close - stop_price
                )
                if shares_to_buy == 0:
                    shares_to_buy = 1
                shares_to_buy -= positions.get(symbol, 0)
                if shares_to_buy <= 0:
                    return

                print('Submitting buy for {} shares of {} at {}'.format(
                    shares_to_buy, symbol, data.close
                ))
                try:
                    o = api.submit_order(
                        symbol=symbol, qty=str(shares_to_buy), side='buy',
                        type='limit', time_in_force='day',
                        limit_price=str(data.close)
                    )
                    open_orders[symbol] = o
                    latest_cost_basis[symbol] = data.close
                except Exception as e:
                    print(e)
                return
        if(
            since_market_open.seconds // 60 >= 24 and
            until_market_close.seconds // 60 > 15
        ):
            # Check for liquidation signals

            # We can't liquidate if there's no position
            position = positions.get(symbol, 0)
            if position == 0:
                return

            # Sell for a loss if it's fallen below our stop price
            # Sell for a loss if it's below our cost basis and MACD < 0
            # Sell for a profit if it's above our target price
            hist = macd(
                minute_history[symbol]['close'].dropna(),
                n_fast=13,
                n_slow=21
            )
            if (
                data.close <= stop_prices[symbol] or
                (data.close >= target_prices[symbol] and hist[-1] <= 0) or
                (data.close <= latest_cost_basis[symbol] and hist[-1] <= 0)
            ):
                print('Submitting sell for {} shares of {} at {}'.format(
                    position, symbol, data.close
                ))
                try:
                    o = api.submit_order(
                        symbol=symbol, qty=str(position), side='sell',
                        type='limit', time_in_force='day',
                        limit_price=str(data.close)
                    )
                    open_orders[symbol] = o
                    latest_cost_basis[symbol] = data.close
                except Exception as e:
                    print(e)
            return
        elif (
            until_market_close.seconds // 60 <= 15
        ):
            # Liquidate remaining positions on watched symbols at market
            try:
                position = api.get_position(symbol)
            except Exception as e:
                # Exception here indicates that we have no position
                return
            print('Trading over, liquidating remaining position in {}'.format(
                symbol)
            )
            api.submit_order(
                symbol=symbol, qty=position.qty, side='sell',
                type='market', time_in_force='day'
            )
            symbols.remove(symbol)
            if len(symbols) <= 0:
                conn.close()
            conn.deregister([
                'A.{}'.format(symbol),
                'AM.{}'.format(symbol)
            ])

    # Replace aggregated 1s bars with incoming 1m bars
    @conn.on(r'AM$')
    async def handle_minute_bar(conn, channel, data):
        ts = data.start
        ts -= timedelta(microseconds=ts.microsecond)
        minute_history[data.symbol].loc[ts] = [
            data.open,
            data.high,
            data.low,
            data.close,
            data.volume
        ]
        volume_today[data.symbol] += data.volume

    channels = ['trade_updates']
    for symbol in symbols:

        #source of error? Issue with A? (Can't find it in Alpaca documentation)
        #Was A intended to find the Trades? The quotes? This was built with the outdated API
        #I am assuming the channel that is required is Quote? Looking for prices of the symbols? 
        symbol_channels = ['Q.{}'.format(symbol),'AM.{}'.format(symbol),]
        channels += symbol_channels
    print('Watching {} symbols.'.format(len(symbols)))
    run_ws(conn, channels)


def run_ws(conn, channels):
    try:
        conn.run(channels)
    except Exception as e:
        print(e)
        conn.close()
        run_ws(conn, channels)


if __name__ == "__main__":
    # Get when the market opens or opened today
    nyc = timezone('America/New_York')
    today = datetime.today().astimezone(nyc)
    today_str = datetime.today().astimezone(nyc).strftime('%Y-%m-%d')
    calendar = api.get_calendar(start=today_str, end=today_str)[0]
    market_open = today.replace(
        hour=calendar.open.hour,
        minute=calendar.open.minute,
        second=0
    )
    market_open = market_open.astimezone(nyc)
    market_close = today.replace(
        hour=calendar.close.hour,
        minute=calendar.close.minute,
        second=0
    )
    market_close = market_close.astimezone(nyc)

    # Wait until just before we might want to trade
    current_dt = datetime.today().astimezone(nyc)
    since_market_open = current_dt - market_open
    while since_market_open.seconds // 60 <= 14:
        time.sleep(1)
        since_market_open = current_dt - market_open

    run(get_tickers(), market_open, market_close)
