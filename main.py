from longport.openapi import Config, QuoteContext, TradeContext, OrderType, OrderSide, TimeInForceType, OutsideRTH
import logging
from decimal import Decimal
from flask import Flask, request, jsonify
import datetime
from flask_cors import CORS
import time
import os
# ==================== Settings ====================
# 做多的ETF
DO_LONG_SYMBOL = "TSLL.US"
# 做空的ETF
DO_SHORT_SYMBOL = "TSDD.US"


# ==================== init ====================
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


config = Config.from_env()
trade_ctx = TradeContext(config)
quote_ctx = QuoteContext(config)

class Action:
    BUY = "buy"
    SELL = "sell"

class Sentiment:
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"

# ==================== Function ====================
def get_current_price(action: Action, symbol: str):
    current_price = None
    resp = quote_ctx.depth(symbol)
    if resp.asks and resp.bids:
        if action == Action.BUY:
            if resp.asks[0].price is not None:
                current_price = resp.asks[0].price  # 买入时参考卖一价
            else:
                raise Exception("可能为夜盘，卖一价为空")
        elif action == Action.SELL:
            if resp.bids[0].price is not None:
                current_price = resp.bids[0].price  # 卖出时参考买一价
            else:
                raise Exception("可能为夜盘，买一价为空")
    else:
        raise Exception("当前无盘口数据...")
    return current_price


def get_current_buy_price(symbol: str):
    return get_current_price(Action.BUY, symbol)

def get_current_sell_price(symbol: str):
    return get_current_price(Action.SELL, symbol)

def buy(symbol: str):
    try:
        current_price = get_current_buy_price(symbol)
        # 获取最大买入数量
        max_buy_resp = trade_ctx.estimate_max_purchase_quantity(
            symbol=symbol,
            order_type=OrderType.LO,
            side=OrderSide.Buy,
            price=current_price
        )
        logger.info(f"最大买入数量: {max_buy_resp.cash_max_qty}")
        # 90%的现金仓位
        quantity = int(int(max_buy_resp.cash_max_qty) * 0.9)
        quantity = 1
        trade_ctx.submit_order(
            symbol,
            OrderType.LO,
            OrderSide.Buy,
            Decimal(quantity),
            TimeInForceType.GoodTilCanceled,

            submitted_price=current_price,
            outside_rth=OutsideRTH.AnyTime,
            remark=f"{'多头' if DO_LONG_SYMBOL == symbol else '空头'}买入"
        )

        logger.info(f"买入订单执行完成 - 股票：{symbol}，数量：{quantity}")
    except Exception as e:
        logger.error(f"买入执行失败：{e}")


def sell(symbol: str, quantity: int):
    try:
        current_price = get_current_sell_price(symbol)
        trade_ctx.submit_order(
            symbol,
            OrderType.LO,
            OrderSide.Sell,
            Decimal(quantity),
            TimeInForceType.GoodTilCanceled,

            submitted_price=current_price,
            outside_rth=OutsideRTH.AnyTime,
            remark=f"{'多头' if DO_LONG_SYMBOL == symbol else '空头'}卖出"
        )
        logger.info(f"卖出订单执行完成 - 股票：{symbol}，数量：{quantity}")
    except Exception as e:
        logger.error(f"卖出执行失败：{e}")


def do_long():
    """
    做多
    """
    buy(DO_LONG_SYMBOL)
    

def do_short():
    """
    做空
    """
    buy(DO_SHORT_SYMBOL)


def do_close_position():
    """
    平仓
    """
    # 获取持仓信息
    stock_positions = []
    try:
        resp = trade_ctx.stock_positions()
        stock_positions = resp.channels
    except Exception as e:
        logger.error(f"获取持仓数量失败：{e}")

    # 平仓动作
    for channel in stock_positions:
        for position in channel.positions:
            if position.symbol == DO_LONG_SYMBOL or position.symbol == DO_SHORT_SYMBOL:
                if position.quantity > 0 and position.quantity < 1:
                    # 碎骨单
                    logger.error(f"{position.symbol} 只剩碎骨单，不用平仓")
                elif position.quantity <= 0:
                    logger.error(f"当前无多头/空头持仓")
                else:
                    sell(position.symbol, position.quantity)
            else:
                logger.error(f"当前无多头/空头持仓")
    
    # 每2秒循环检测持仓，直到用于没有任何持仓
    while True:
        time.sleep(2)
        resp = trade_ctx.stock_positions()
        stock_positions = resp.channels
        LONG_POSITION = False
        SHORT_POSITION = False
        for channel in stock_positions:
            for position in channel.positions:
                if position.symbol == DO_LONG_SYMBOL and position.quantity > 1:
                    LONG_POSITION = True
                elif position.symbol == DO_SHORT_SYMBOL and position.quantity > 1:
                    SHORT_POSITION = True
        
        # 两者同时没有持仓时，才算平仓完成
        if LONG_POSITION and SHORT_POSITION:
            continue
        else:
            break    


# ==================== Main ====================
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        webhook_data = request.json
        logger.info(f"收到TradingView信号=======>")
        logger.info(f"{webhook_data}")
        
        # 获取交易动作和市场位置信息
        action = webhook_data.get('action')
        sentiment = webhook_data.get('sentiment')
        
        if not action or not sentiment:
            """
            {
                "ticker": "{{ticker}}",
                "time": "{{time}}",
                "action": "{{strategy.order.action}}",
                "sentiment": "{{strategy.market_position}}",
                "price": "{{strategy.order.price}}"
            }
            """
            logger.error("信号数据不完整，缺少action或sentiment")
            return jsonify({'error': '信号数据不完整'}), 400
            
        logger.info(f"交易信号: action={action}, position={sentiment}")
        
        # 根据信号执行交易
        if action == Action.BUY and sentiment == Sentiment.LONG:
            # 开多仓
            logger.info("执行开多仓操作")
            do_close_position()
            do_long()
        elif action == Action.SELL and sentiment == Sentiment.SHORT:
            # 开空仓
            logger.info("执行开空仓操作")
            do_close_position()
            do_short()
        elif (action == Action.SELL and sentiment == Sentiment.FLAT) or (action == Action.BUY and sentiment == Sentiment.FLAT):
            # 平仓操作
            logger.info("执行平仓操作")
            do_close_position()
        else:
            logger.warning(f"未识别的交易信号组合: action={action}, position={sentiment}")
        
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"处理webhook时出错: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/webhook_test', methods=['POST'])
def webhook_test():
    webhook_data = request.json
    logger.info(f"收到TradingView信号=======>")
    logger.info(f"{webhook_data}")

if __name__ == '__main__':
    logger.info("启动成功，当前北京时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    app.run(host='0.0.0.0', port=80, debug=True)
