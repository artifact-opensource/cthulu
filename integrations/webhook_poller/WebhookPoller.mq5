//+------------------------------------------------------------------+
//| WebhookPoller.mq5                                               |
//| EA to poll a local webhook server and execute BUY/SELL commands  |
//| Command format: "<id>|<CMD>|<SYMBOL>|<VOLUME>|<PRICE>|<SL>|<TP>"|
//+------------------------------------------------------------------+
#property copyright "Cthulu"
#property version   "2.0"
#property strict

input string ServerUrl = "http://127.0.0.1:9002"; // add to WebRequest allowed URLs
input string WebhookSecret = "";                    // optional HMAC/API key
input int    PollInterval = 5;                      // seconds between polls

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(PollInterval);
   Print("WebhookPoller v2.0 initialized, polling ", ServerUrl, "/next_job every ", PollInterval, "s");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   string url = ServerUrl + "/next_job";
   uchar post_data[];
   uchar result[];
   string res_headers;
   int timeout = 10000;
   
   string headers = "";
   if(StringLen(WebhookSecret) > 0)
      headers = "X-API-KEY: " + WebhookSecret + "\r\n";
   
   int res = WebRequest("GET", url, headers, timeout, post_data, result, res_headers);
   
   if(res == 200 && ArraySize(result) > 0)
     {
      string resText = CharArrayToString(result, 0, ArraySize(result), CP_UTF8);
      Print("Received job: ", resText);
      
      // Parse: id|CMD|SYMBOL|VOLUME|PRICE|SL|TP|ORDERTYPE
      string parts[];
      int n = StringSplit(resText, '|', parts);
      
      if(n >= 7)
        {
         int    job_id    = (int)StringToInteger(parts[0]);
         string cmd       = parts[1];
         string symbol    = parts[2];
         double volume    = StringToDouble(parts[3]);
         double price     = StringToDouble(parts[4]);
         double sl        = StringToDouble(parts[5]);
         double tp        = StringToDouble(parts[6]);
         string order_type = "market";
         if(n >= 8) order_type = parts[7];
         
         bool success = ExecuteOrder(cmd, symbol, volume, price, sl, tp, order_type);
         
         if(success)
           {
            AckJob(job_id);
           }
        }
      else
        {
         Print("Malformed job response (", n, " fields): ", resText);
        }
     }
   else if(res != 0 && res != 204)
     {
      // Only log errors, not 204 (no job) or 0 (connection refused)
      if(res > 0)
         Print("Server error, status=", res);
     }
  }

//+------------------------------------------------------------------+
bool ExecuteOrder(string cmd, string symbol, double volume, double price, 
                  double sl, double tp, string order_type)
  {
   MqlTradeRequest request;
   MqlTradeResult  result;
   ZeroMemory(request);
   ZeroMemory(result);
   
   // Ensure symbol is selected
   if(!SymbolSelect(symbol, true))
     {
      Print("Failed to select symbol: ", symbol);
      return false;
     }
   
   // Determine order type
   if(order_type == "limit" && price > 0)
     {
      request.action = TRADE_ACTION_PENDING;
      if(cmd == "BUY")
         request.type = ORDER_TYPE_BUY_LIMIT;
      else if(cmd == "SELL")
         request.type = ORDER_TYPE_SELL_LIMIT;
      else
        { Print("Unknown cmd for limit: ", cmd); return false; }
      request.price = price;
     }
   else if(order_type == "stop" && price > 0)
     {
      request.action = TRADE_ACTION_PENDING;
      if(cmd == "BUY")
         request.type = ORDER_TYPE_BUY_STOP;
      else if(cmd == "SELL")
         request.type = ORDER_TYPE_SELL_STOP;
      else
        { Print("Unknown cmd for stop: ", cmd); return false; }
      request.price = price;
     }
   else
     {
      // Market order
      request.action = TRADE_ACTION_DEAL;
      if(cmd == "BUY")
        {
         request.type = ORDER_TYPE_BUY;
         request.price = SymbolInfoDouble(symbol, SYMBOL_ASK);
        }
      else if(cmd == "SELL")
        {
         request.type = ORDER_TYPE_SELL;
         request.price = SymbolInfoDouble(symbol, SYMBOL_BID);
        }
      else if(cmd == "CLOSE_BUY" || cmd == "CLOSE_SELL")
        {
         return ClosePosition(symbol, volume, cmd);
        }
      else if(cmd == "MODIFY")
        {
         return ModifyPosition(symbol, sl, tp);
        }
      else
        { Print("Unknown cmd: ", cmd); return false; }
     }
   
   request.symbol = symbol;
   request.volume = volume;
   if(sl > 0) request.sl = sl;
   if(tp > 0) request.tp = tp;
   request.type_filling = ORDER_FILLING_IOC;
   request.type_time = ORDER_TIME_GTC;
   request.magic = 123456; // Cthulu magic number
   request.comment = "Cthulu";
   
   if(!OrderSend(request, result))
     {
      Print("OrderSend failed: ", GetLastError(), " retcode=", result.retcode);
      return false;
     }
   
   PrintFormat("Order executed: ticket=%I64d, retcode=%u, price=%.5f", 
               result.order, result.retcode, result.price);
   return (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED);
  }

//+------------------------------------------------------------------+
bool ClosePosition(string symbol, double volume, string cmd)
  {
   // Find open position for symbol
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == symbol)
        {
         long pos_type = PositionGetInteger(POSITION_TYPE);
         if((cmd == "CLOSE_BUY" && pos_type == POSITION_TYPE_BUY) ||
            (cmd == "CLOSE_SELL" && pos_type == POSITION_TYPE_SELL))
           {
            MqlTradeRequest request;
            MqlTradeResult  result;
            ZeroMemory(request);
            ZeroMemory(result);
            
            request.action = TRADE_ACTION_DEAL;
            request.position = ticket;
            request.symbol = symbol;
            request.volume = (volume > 0) ? volume : PositionGetDouble(POSITION_VOLUME);
            request.type = (pos_type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            request.price = (pos_type == POSITION_TYPE_BUY) ? 
                           SymbolInfoDouble(symbol, SYMBOL_BID) : 
                           SymbolInfoDouble(symbol, SYMBOL_ASK);
            request.type_filling = ORDER_FILLING_IOC;
            request.magic = 123456;
            
            if(OrderSend(request, result))
              {
               PrintFormat("Position closed: ticket=%I64d, retcode=%u", ticket, result.retcode);
               return true;
              }
            else
              {
               Print("Close failed: ", GetLastError());
               return false;
              }
           }
        }
     }
   Print("No matching position found for ", cmd, " ", symbol);
   return false;
  }

//+------------------------------------------------------------------+
bool ModifyPosition(string symbol, double sl, double tp)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == symbol)
        {
         MqlTradeRequest request;
         MqlTradeResult  result;
         ZeroMemory(request);
         ZeroMemory(result);
         
         request.action = TRADE_ACTION_SLTP;
         request.position = ticket;
         request.symbol = symbol;
         if(sl > 0) request.sl = sl;
         if(tp > 0) request.tp = tp;
         
         if(OrderSend(request, result))
           {
            PrintFormat("Position modified: ticket=%I64d, SL=%.5f, TP=%.5f", ticket, sl, tp);
            return true;
           }
         else
           {
            Print("Modify failed: ", GetLastError());
            return false;
           }
        }
     }
   Print("No position found for ", symbol);
   return false;
  }

//+------------------------------------------------------------------+
void AckJob(int job_id)
  {
   string ackUrl = ServerUrl + "/ack?id=" + IntegerToString(job_id);
   string headers = "Content-Type: application/json\r\n";
   if(StringLen(WebhookSecret) > 0)
      headers = headers + "X-API-KEY: " + WebhookSecret + "\r\n";
   
   uchar post_data[];
   uchar ack_result[];
   string ack_headers;
   
   int ackRes = WebRequest("POST", ackUrl, headers, 5000, post_data, ack_result, ack_headers);
   Print("Job ", job_id, " ack: ", ackRes);
  }
//+------------------------------------------------------------------+
