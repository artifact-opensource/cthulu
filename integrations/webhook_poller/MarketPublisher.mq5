//+------------------------------------------------------------------+
//| MarketPublisher.mq5                                              |
//| EA that publishes ticks and completed bars to webhook server.    |
//+------------------------------------------------------------------+
#property copyright "Cthulu"
#property version   "1.0"
#property strict

input string ServerUrl = "http://127.0.0.1:9002"; // Server base
input string WebhookSecret = ""; // Optional: set your WEBHOOK_SECRET here to send X-API-KEY header
input bool   PublishTicks = true;
input bool   PublishBars = true;
input int    BarTFSeconds = 60; // seconds for bar timeframe, EA collects OHLC

datetime lastBarTime = 0;
double barOpen, barHigh, barLow, barClose;

int OnInit()
  {
   Print("MarketPublisher initialized, server=", ServerUrl);
   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   if(PublishTicks)
     {
      // Build tick payload
      // Build JSON payload without StringFormat to avoid compiler format issues
      int digits = (int)SymbolInfoInteger(Symbol(), SYMBOL_DIGITS);
      string bid_s = DoubleToString(SymbolInfoDouble(Symbol(), SYMBOL_BID), digits);
      string ask_s = DoubleToString(SymbolInfoDouble(Symbol(), SYMBOL_ASK), digits);
      string payload = "{\"symbol\":\"" + Symbol() + "\",\"bid\":" + bid_s + ",\"ask\":" + ask_s + ",\"time\":\"" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\"}";
      // send
      uchar data[];
      int data_len = StringToCharArray(payload, data);
      uchar res[];
      string res_headers;
      int timeout = 5000;
      string headers = "Content-Type: application/json\r\n";
      if(StringLen(WebhookSecret)>0) headers = headers + "X-API-KEY: " + WebhookSecret + "\r\n";
      int status = WebRequest("POST", ServerUrl + "/publish_tick", headers, timeout, data, res, res_headers);
      if(status!=200 && status!=201)
         Print("Tick publish failed, status=", status);
     }

   // Bar aggregation (simple, based on time)
   if(PublishBars)
     {
      datetime t = TimeCurrent();
      int period = BarTFSeconds;
      datetime curBarStart = (datetime)(t - t%period);
      if(curBarStart!=lastBarTime)
        {
         // close previous bar
         if(lastBarTime!=0)
           {
            // Build bar JSON without StringFormat
            int digits = (int)SymbolInfoInteger(Symbol(), SYMBOL_DIGITS);
            string open_s = DoubleToString(barOpen, digits);
            string high_s = DoubleToString(barHigh, digits);
            string low_s = DoubleToString(barLow, digits);
            string close_s = DoubleToString(barClose, digits);
            string bpayload = "{\"symbol\":\"" + Symbol() + "\",\"timeframe\":\"" + TimeframeToString(period) + "\",\"time\":\"" + TimeToString(lastBarTime, TIME_DATE|TIME_SECONDS) + "\",\"open\":" + open_s + ",\"high\":" + high_s + ",\"low\":" + low_s + ",\"close\":" + close_s + ",\"volume\":0}";
            uchar bdata[];
            int bdata_len = StringToCharArray(bpayload, bdata);
            uchar bres[];
            string bres_headers;
            string bheaders = "Content-Type: application/json\r\n";
            if(StringLen(WebhookSecret)>0) bheaders = bheaders + "X-API-KEY: " + WebhookSecret + "\r\n";
            int bstatus = WebRequest("POST", ServerUrl + "/publish_bar", bheaders, 5000, bdata, bres, bres_headers);
            if(bstatus!=200 && bstatus!=201)
               Print("Bar publish failed, status=", bstatus);
           }
         // start new bar
         lastBarTime = curBarStart;
         barOpen = barHigh = barLow = barClose = SymbolInfoDouble(Symbol(), SYMBOL_BID);
        }
      else
        {
         double price = SymbolInfoDouble(Symbol(), SYMBOL_BID);
         barClose = price;
         if(price>barHigh) barHigh = price;
         if(price<barLow) barLow = price;
        }
     }
  }

string TimeframeToString(int secs)
  {
   if(secs==60) return "M1";
   if(secs==300) return "M5";
   if(secs==900) return "M15";
   if(secs==3600) return "H1";
   return IntegerToString(secs) + "s";
  }

void OnDeinit(const int reason)
  {
   // cleanup if needed
  }

//+------------------------------------------------------------------+
