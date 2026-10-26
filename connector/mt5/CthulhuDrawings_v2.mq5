//+------------------------------------------------------------------+
//|                                           CthulhuDrawings_v2.mq5 |
//|                                  Cthulu v5.2.33 - Chart Manager |
//|                      Multi-Timeframe Zone Drawing from JSON v2   |
//+------------------------------------------------------------------+
#property copyright "Cthulu Trading System"
#property link      "https://github.com/cthulu"
#property version   "2.00"
#property indicator_chart_window
#property indicator_plots 0

//--- Input parameters
input int      RefreshSeconds = 3;           // Refresh interval (seconds)
input bool     DrawZones = true;             // Draw zone rectangles
input bool     DrawLevels = true;            // Draw horizontal levels
input bool     DrawTrendLines = true;        // Draw trend lines
input bool     ShowLabels = true;            // Show zone labels
input bool     ShowMTFZones = true;          // Show zones from all timeframes
input int      ZoneHistoryBars = 100;        // How many bars back to draw zones
input int      ZoneForwardBars = 20;         // Extend zones forward (bars)
input bool     FilterByCurrentTF = false;    // Only show current TF zones
input int      MinZoneStrength = 30;         // Min strength % to display (0-100)

//--- Timeframe filters
input bool     ShowM30Zones = true;          // Show M30 zones
input bool     ShowH1Zones = true;           // Show H1 zones
input bool     ShowH4Zones = true;           // Show H4 zones
input bool     ShowD1Zones = true;           // Show D1 zones

//--- Visual settings
input color    BullishOBColor = clrLime;           // Bullish OB color
input color    BearishOBColor = clrRed;            // Bearish OB color
input color    ORBColor = clrGold;                 // ORB color
input color    SupportColor = clrDodgerBlue;       // Support color
input color    ResistanceColor = clrOrangeRed;     // Resistance color

//--- Object prefix for cleanup
#define OBJ_PREFIX "CTH2_"

//--- Global variables
string g_currentSymbol;
string g_currentTimeframe;
datetime g_lastModified = 0;

//+------------------------------------------------------------------+
//| Custom indicator initialization                                    |
//+------------------------------------------------------------------+
int OnInit()
{
    g_currentSymbol = Symbol();
    g_currentTimeframe = GetTimeframeString(Period());
    
    Print("=== CthulhuDrawings v2.0 (MTF) ===");
    Print("Symbol: ", g_currentSymbol, " Timeframe: ", g_currentTimeframe);
    Print("MTF Zones: ", ShowMTFZones ? "Enabled" : "Disabled");
    
    // Initial load
    LoadAndDrawAll();
    
    // Set timer
    EventSetTimer(RefreshSeconds);
    
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Custom indicator deinitialization                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    CleanupAllObjects();
    Print("CthulhuDrawings v2 removed from chart");
}

//+------------------------------------------------------------------+
//| Timer function                                                     |
//+------------------------------------------------------------------+
void OnTimer()
{
    LoadAndDrawAll();
}

//+------------------------------------------------------------------+
//| Main calculation function                                          |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
    return(rates_total);
}

//+------------------------------------------------------------------+
//| Load JSON and draw all objects                                    |
//+------------------------------------------------------------------+
void LoadAndDrawAll()
{
    string safeSymbol = g_currentSymbol;
    StringReplace(safeSymbol, "#", "");
    StringReplace(safeSymbol, "/", "_");
    
    // Try MTF file first (new format), then fallback to single TF
    string mtfFilename = safeSymbol + "_MTF_drawings.json";
    string singleFilename = safeSymbol + "_" + g_currentTimeframe + "_drawings.json";
    
    string jsonContent = "";
    bool found = false;
    
    // Try MTF file in common folder
    int handle = FileOpen(mtfFilename, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
    if(handle != INVALID_HANDLE)
    {
        while(!FileIsEnding(handle))
            jsonContent += FileReadString(handle) + "\n";
        FileClose(handle);
        found = true;
        Print("Loaded MTF drawings: ", mtfFilename);
    }
    
    // Fallback to single TF file
    if(!found)
    {
        handle = FileOpen(singleFilename, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
        if(handle != INVALID_HANDLE)
        {
            while(!FileIsEnding(handle))
                jsonContent += FileReadString(handle) + "\n";
            FileClose(handle);
            found = true;
            Print("Loaded single TF drawings: ", singleFilename);
        }
    }
    
    // Try MQL5/Files as last resort
    if(!found)
    {
        handle = FileOpen(mtfFilename, FILE_READ|FILE_TXT|FILE_ANSI);
        if(handle != INVALID_HANDLE)
        {
            while(!FileIsEnding(handle))
                jsonContent += FileReadString(handle) + "\n";
            FileClose(handle);
            found = true;
        }
    }
    
    if(!found || StringLen(jsonContent) < 20)
    {
        // Only warn occasionally
        static datetime lastWarning = 0;
        if(TimeCurrent() - lastWarning > 60)
        {
            Print("No drawings file found. Ensure Cthulu is running.");
            lastWarning = TimeCurrent();
        }
        return;
    }
    
    // Parse and draw
    ParseAndDraw(jsonContent);
}

//+------------------------------------------------------------------+
//| Parse JSON and draw objects                                       |
//+------------------------------------------------------------------+
void ParseAndDraw(string &json)
{
    // Clean up old objects
    CleanupAllObjects();
    
    int zonesDrawn = 0;
    int levelsDrawn = 0;
    int trendlinesDrawn = 0;
    
    // Parse zones
    if(DrawZones)
        zonesDrawn = ParseAndDrawZones(json);
    
    // Parse levels
    if(DrawLevels)
        levelsDrawn = ParseAndDrawLevels(json);
    
    // Parse trend lines
    if(DrawTrendLines)
        trendlinesDrawn = ParseAndDrawTrendLines(json);
    
    ChartRedraw();
    
    Print("Drew: ", zonesDrawn, " zones, ", levelsDrawn, " levels, ", trendlinesDrawn, " trendlines");
}

//+------------------------------------------------------------------+
//| Parse and draw zones from JSON v2 format                          |
//+------------------------------------------------------------------+
int ParseAndDrawZones(string &json)
{
    int zonesStart = StringFind(json, "\"zones\":");
    if(zonesStart < 0) return 0;
    
    int arrayStart = StringFind(json, "[", zonesStart);
    if(arrayStart < 0) return 0;
    
    // Find array end
    int bracketCount = 1;
    int pos = arrayStart + 1;
    int len = StringLen(json);
    while(pos < len && bracketCount > 0)
    {
        string ch = StringSubstr(json, pos, 1);
        if(ch == "[") bracketCount++;
        else if(ch == "]") bracketCount--;
        pos++;
    }
    
    string zonesArray = StringSubstr(json, arrayStart, pos - arrayStart);
    
    int zoneCount = 0;
    int searchPos = 0;
    
    while(true)
    {
        int objStart = StringFind(zonesArray, "{", searchPos);
        if(objStart < 0) break;
        
        // Find matching closing brace (handle nested objects)
        int braceCount = 1;
        int objEnd = objStart + 1;
        while(objEnd < StringLen(zonesArray) && braceCount > 0)
        {
            string c = StringSubstr(zonesArray, objEnd, 1);
            if(c == "{") braceCount++;
            else if(c == "}") braceCount--;
            objEnd++;
        }
        
        string zoneObj = StringSubstr(zonesArray, objStart, objEnd - objStart);
        
        // Extract zone properties
        string id = ExtractJsonString(zoneObj, "id");
        string type = ExtractJsonString(zoneObj, "type");
        double upper = ExtractJsonDouble(zoneObj, "upper");
        double lower = ExtractJsonDouble(zoneObj, "lower");
        string colorHex = ExtractJsonString(zoneObj, "color");
        string state = ExtractJsonString(zoneObj, "state");
        double strength = ExtractJsonDouble(zoneObj, "strength");
        string timeframe = ExtractJsonString(zoneObj, "timeframe");
        int priority = (int)ExtractJsonDouble(zoneObj, "priority");
        string startTimeStr = ExtractJsonString(zoneObj, "start_time");
        
        // Filter by timeframe if enabled
        if(FilterByCurrentTF && timeframe != g_currentTimeframe)
        {
            searchPos = objEnd;
            continue;
        }
        
        // Filter by timeframe toggles
        if(!ShouldShowTimeframe(timeframe))
        {
            searchPos = objEnd;
            continue;
        }
        
        // Filter by strength
        if(strength * 100 < MinZoneStrength)
        {
            searchPos = objEnd;
            continue;
        }
        
        // Draw the zone
        if(upper > 0 && lower > 0)
        {
            DrawZone(id, type, upper, lower, colorHex, state, strength, timeframe, priority, startTimeStr);
            zoneCount++;
        }
        
        searchPos = objEnd;
    }
    
    return zoneCount;
}

//+------------------------------------------------------------------+
//| Check if timeframe should be displayed                            |
//+------------------------------------------------------------------+
bool ShouldShowTimeframe(string tf)
{
    if(!ShowMTFZones) return (tf == g_currentTimeframe);
    
    if(tf == "M30" && !ShowM30Zones) return false;
    if(tf == "H1" && !ShowH1Zones) return false;
    if(tf == "H4" && !ShowH4Zones) return false;
    if(tf == "D1" && !ShowD1Zones) return false;
    
    return true;
}

//+------------------------------------------------------------------+
//| Draw a single zone with proper historical context                 |
//+------------------------------------------------------------------+
void DrawZone(string id, string type, double upper, double lower,
              string colorHex, string state, double strength, 
              string timeframe, int priority, string startTimeStr)
{
    string objName = OBJ_PREFIX + "ZONE_" + id;
    
    // Parse start time or use default
    datetime zoneStartTime;
    if(StringLen(startTimeStr) > 10)
    {
        // Parse ISO timestamp (simplified - just use bar history)
        zoneStartTime = iTime(g_currentSymbol, Period(), ZoneHistoryBars);
    }
    else
    {
        zoneStartTime = iTime(g_currentSymbol, Period(), ZoneHistoryBars);
    }
    
    // End time extends forward
    datetime zoneEndTime = iTime(g_currentSymbol, Period(), 0) + PeriodSeconds(Period()) * ZoneForwardBars;
    
    // Get color
    color zoneColor = GetZoneColor(type, colorHex);
    
    // Adjust color intensity based on timeframe priority
    // Higher TF zones are more prominent
    
    // Create rectangle
    if(!ObjectCreate(0, objName, OBJ_RECTANGLE, 0, zoneStartTime, upper, zoneEndTime, lower))
    {
        Print("Failed to create zone: ", objName);
        return;
    }
    
    ObjectSetInteger(0, objName, OBJPROP_COLOR, zoneColor);
    ObjectSetInteger(0, objName, OBJPROP_FILL, true);
    ObjectSetInteger(0, objName, OBJPROP_BACK, true);
    
    // Style based on state
    ENUM_LINE_STYLE lineStyle = STYLE_SOLID;
    if(state == "TESTED" || state == "WEAKENED")
        lineStyle = STYLE_DASH;
    ObjectSetInteger(0, objName, OBJPROP_STYLE, lineStyle);
    
    // Width based on priority (higher TF = thicker border)
    int width = 1 + MathMax(0, priority - 4);
    ObjectSetInteger(0, objName, OBJPROP_WIDTH, width);
    
    ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, true);
    ObjectSetInteger(0, objName, OBJPROP_HIDDEN, false);
    
    // Tooltip with zone info
    string tooltip = StringFormat("%s [%s]\nRange: %.2f - %.2f\nStrength: %.0f%%\nState: %s",
                                  GetZoneTypeName(type), timeframe,
                                  lower, upper, strength * 100, state);
    ObjectSetString(0, objName, OBJPROP_TOOLTIP, tooltip);
    
    // Add label
    if(ShowLabels)
    {
        string labelName = OBJ_PREFIX + "LBL_" + id;
        double midPrice = (upper + lower) / 2;
        
        if(ObjectCreate(0, labelName, OBJ_TEXT, 0, zoneStartTime, midPrice))
        {
            string labelText = GetZoneLabel(type, timeframe, strength);
            ObjectSetString(0, labelName, OBJPROP_TEXT, labelText);
            ObjectSetInteger(0, labelName, OBJPROP_COLOR, zoneColor);
            ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);
            ObjectSetString(0, labelName, OBJPROP_FONT, "Arial Bold");
            ObjectSetInteger(0, labelName, OBJPROP_ANCHOR, ANCHOR_LEFT);
        }
    }
}

//+------------------------------------------------------------------+
//| Get zone color from type or hex                                   |
//+------------------------------------------------------------------+
color GetZoneColor(string type, string hexColor)
{
    // Use type-based colors for consistency
    if(type == "ob_bullish") return BullishOBColor;
    if(type == "ob_bearish") return BearishOBColor;
    if(type == "orb_high" || type == "orb_low") return ORBColor;
    if(type == "support") return SupportColor;
    if(type == "resistance") return ResistanceColor;
    if(type == "fvg_bullish") return clrLimeGreen;
    if(type == "fvg_bearish") return clrCrimson;
    
    // Fallback to hex color
    return HexToColor(hexColor);
}

//+------------------------------------------------------------------+
//| Get zone type display name                                        |
//+------------------------------------------------------------------+
string GetZoneTypeName(string type)
{
    if(type == "ob_bullish") return "Bullish Order Block";
    if(type == "ob_bearish") return "Bearish Order Block";
    if(type == "orb_high") return "ORB High";
    if(type == "orb_low") return "ORB Low";
    if(type == "support") return "Support";
    if(type == "resistance") return "Resistance";
    if(type == "fvg_bullish") return "Bullish FVG";
    if(type == "fvg_bearish") return "Bearish FVG";
    return type;
}

//+------------------------------------------------------------------+
//| Get zone label text                                               |
//+------------------------------------------------------------------+
string GetZoneLabel(string type, string timeframe, double strength)
{
    string label = "";
    
    // Zone type abbreviation
    if(type == "ob_bullish") label = "OB+";
    else if(type == "ob_bearish") label = "OB-";
    else if(type == "orb_high") label = "ORB-H";
    else if(type == "orb_low") label = "ORB-L";
    else if(type == "support") label = "SUP";
    else if(type == "resistance") label = "RES";
    else if(type == "fvg_bullish") label = "FVG+";
    else if(type == "fvg_bearish") label = "FVG-";
    else label = type;
    
    // Add timeframe tag
    label += " [" + timeframe + "]";
    
    // Add strength indicator
    if(strength >= 0.8) label += " ★★★";
    else if(strength >= 0.5) label += " ★★";
    else if(strength >= 0.3) label += " ★";
    
    return label;
}

//+------------------------------------------------------------------+
//| Parse and draw levels                                             |
//+------------------------------------------------------------------+
int ParseAndDrawLevels(string &json)
{
    int levelsStart = StringFind(json, "\"levels\":");
    if(levelsStart < 0) return 0;
    
    int arrayStart = StringFind(json, "[", levelsStart);
    if(arrayStart < 0) return 0;
    
    int bracketCount = 1;
    int pos = arrayStart + 1;
    int len = StringLen(json);
    while(pos < len && bracketCount > 0)
    {
        string ch = StringSubstr(json, pos, 1);
        if(ch == "[") bracketCount++;
        else if(ch == "]") bracketCount--;
        pos++;
    }
    
    string levelsArray = StringSubstr(json, arrayStart, pos - arrayStart);
    
    int levelCount = 0;
    int searchPos = 0;
    
    while(true)
    {
        int objStart = StringFind(levelsArray, "{", searchPos);
        if(objStart < 0) break;
        
        int objEnd = StringFind(levelsArray, "}", objStart);
        if(objEnd < 0) break;
        
        string levelObj = StringSubstr(levelsArray, objStart, objEnd - objStart + 1);
        
        double price = ExtractJsonDouble(levelObj, "price");
        string type = ExtractJsonString(levelObj, "type");
        string colorHex = ExtractJsonString(levelObj, "color");
        string label = ExtractJsonString(levelObj, "label");
        string style = ExtractJsonString(levelObj, "style");
        int width = (int)ExtractJsonDouble(levelObj, "width");
        string timeframe = ExtractJsonString(levelObj, "timeframe");
        
        if(price > 0)
        {
            DrawLevel(levelCount, price, type, colorHex, label, style, width, timeframe);
            levelCount++;
        }
        
        searchPos = objEnd + 1;
    }
    
    return levelCount;
}

//+------------------------------------------------------------------+
//| Draw a horizontal level                                           |
//+------------------------------------------------------------------+
void DrawLevel(int index, double price, string type, string colorHex,
               string label, string style, int width, string timeframe)
{
    string objName = OBJ_PREFIX + "LVL_" + IntegerToString(index);
    
    color levelColor = (type == "support") ? SupportColor : ResistanceColor;
    if(StringLen(colorHex) == 7)
        levelColor = HexToColor(colorHex);
    
    ENUM_LINE_STYLE lineStyle = STYLE_DOT;
    if(style == "solid") lineStyle = STYLE_SOLID;
    else if(style == "dashed") lineStyle = STYLE_DASH;
    
    if(width < 1) width = 1;
    
    if(ObjectCreate(0, objName, OBJ_HLINE, 0, 0, price))
    {
        ObjectSetInteger(0, objName, OBJPROP_COLOR, levelColor);
        ObjectSetInteger(0, objName, OBJPROP_STYLE, lineStyle);
        ObjectSetInteger(0, objName, OBJPROP_WIDTH, width);
        ObjectSetInteger(0, objName, OBJPROP_BACK, true);
        ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, true);
        
        // Add label to tooltip
        string tooltip = label;
        if(StringLen(timeframe) > 0)
            tooltip += " [" + timeframe + "]";
        ObjectSetString(0, objName, OBJPROP_TOOLTIP, tooltip);
        
        if(ShowLabels && StringLen(label) > 0)
            ObjectSetString(0, objName, OBJPROP_TEXT, label);
    }
}

//+------------------------------------------------------------------+
//| Parse and draw trend lines                                        |
//+------------------------------------------------------------------+
int ParseAndDrawTrendLines(string &json)
{
    int tlStart = StringFind(json, "\"trend_lines\":");
    if(tlStart < 0) return 0;
    
    int arrayStart = StringFind(json, "[", tlStart);
    if(arrayStart < 0) return 0;
    
    int bracketCount = 1;
    int pos = arrayStart + 1;
    int len = StringLen(json);
    while(pos < len && bracketCount > 0)
    {
        string ch = StringSubstr(json, pos, 1);
        if(ch == "[") bracketCount++;
        else if(ch == "]") bracketCount--;
        pos++;
    }
    
    string tlArray = StringSubstr(json, arrayStart, pos - arrayStart);
    
    int tlCount = 0;
    int searchPos = 0;
    
    while(true)
    {
        int objStart = StringFind(tlArray, "{", searchPos);
        if(objStart < 0) break;
        
        int objEnd = StringFind(tlArray, "}", objStart);
        if(objEnd < 0) break;
        
        string tlObj = StringSubstr(tlArray, objStart, objEnd - objStart + 1);
        
        string id = ExtractJsonString(tlObj, "id");
        double startPrice = ExtractJsonDouble(tlObj, "start_price");
        double endPrice = ExtractJsonDouble(tlObj, "end_price");
        string colorHex = ExtractJsonString(tlObj, "color");
        string style = ExtractJsonString(tlObj, "style");
        int width = (int)ExtractJsonDouble(tlObj, "width");
        
        if(startPrice > 0 && endPrice > 0)
        {
            DrawTrendLine(tlCount, startPrice, endPrice, colorHex, style, width);
            tlCount++;
        }
        
        searchPos = objEnd + 1;
    }
    
    return tlCount;
}

//+------------------------------------------------------------------+
//| Draw a trend line                                                 |
//+------------------------------------------------------------------+
void DrawTrendLine(int index, double startPrice, double endPrice,
                   string colorHex, string style, int width)
{
    string objName = OBJ_PREFIX + "TL_" + IntegerToString(index);
    
    datetime time1 = iTime(g_currentSymbol, Period(), ZoneHistoryBars);
    datetime time2 = iTime(g_currentSymbol, Period(), 0);
    
    color lineColor = HexToColor(colorHex);
    
    ENUM_LINE_STYLE lineStyle = STYLE_SOLID;
    if(style == "dashed") lineStyle = STYLE_DASH;
    else if(style == "dotted") lineStyle = STYLE_DOT;
    
    if(width < 1) width = 2;
    
    if(ObjectCreate(0, objName, OBJ_TREND, 0, time1, startPrice, time2, endPrice))
    {
        ObjectSetInteger(0, objName, OBJPROP_COLOR, lineColor);
        ObjectSetInteger(0, objName, OBJPROP_STYLE, lineStyle);
        ObjectSetInteger(0, objName, OBJPROP_WIDTH, width);
        ObjectSetInteger(0, objName, OBJPROP_RAY_RIGHT, true);
        ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, true);
    }
}

//+------------------------------------------------------------------+
//| Cleanup all Cthulu objects                                        |
//+------------------------------------------------------------------+
void CleanupAllObjects()
{
    int total = ObjectsTotal(0);
    for(int i = total - 1; i >= 0; i--)
    {
        string name = ObjectName(0, i);
        if(StringFind(name, OBJ_PREFIX) == 0)
            ObjectDelete(0, name);
    }
}

//+------------------------------------------------------------------+
//| Extract string value from JSON                                    |
//+------------------------------------------------------------------+
string ExtractJsonString(string &json, string key)
{
    string searchKey = "\"" + key + "\":";
    int keyPos = StringFind(json, searchKey);
    if(keyPos < 0) return "";
    
    int valueStart = keyPos + StringLen(searchKey);
    
    // Skip whitespace
    while(StringSubstr(json, valueStart, 1) == " " || 
          StringSubstr(json, valueStart, 1) == "\t")
        valueStart++;
    
    // Check if string value
    if(StringSubstr(json, valueStart, 1) == "\"")
    {
        valueStart++;
        int valueEnd = StringFind(json, "\"", valueStart);
        if(valueEnd > valueStart)
            return StringSubstr(json, valueStart, valueEnd - valueStart);
    }
    
    return "";
}

//+------------------------------------------------------------------+
//| Extract double value from JSON                                    |
//+------------------------------------------------------------------+
double ExtractJsonDouble(string &json, string key)
{
    string searchKey = "\"" + key + "\":";
    int keyPos = StringFind(json, searchKey);
    if(keyPos < 0) return 0;
    
    int valueStart = keyPos + StringLen(searchKey);
    
    // Skip whitespace
    while(StringSubstr(json, valueStart, 1) == " " || 
          StringSubstr(json, valueStart, 1) == "\t")
        valueStart++;
    
    // Find end of number
    int valueEnd = valueStart;
    int len = StringLen(json);
    while(valueEnd < len)
    {
        string ch = StringSubstr(json, valueEnd, 1);
        if(ch == "," || ch == "}" || ch == "]" || ch == " " || ch == "\n")
            break;
        valueEnd++;
    }
    
    string valueStr = StringSubstr(json, valueStart, valueEnd - valueStart);
    return StringToDouble(valueStr);
}

//+------------------------------------------------------------------+
//| Convert hex color to MT5 color                                    |
//+------------------------------------------------------------------+
color HexToColor(string hex)
{
    if(StringSubstr(hex, 0, 1) == "#")
        hex = StringSubstr(hex, 1);
    
    if(StringLen(hex) != 6)
        return clrGray;
    
    int r = HexCharToInt(StringSubstr(hex, 0, 2));
    int g = HexCharToInt(StringSubstr(hex, 2, 2));
    int b = HexCharToInt(StringSubstr(hex, 4, 2));
    
    return (color)((b << 16) | (g << 8) | r);
}

//+------------------------------------------------------------------+
//| Convert hex string to int                                         |
//+------------------------------------------------------------------+
int HexCharToInt(string hexStr)
{
    int result = 0;
    StringToUpper(hexStr);
    
    for(int i = 0; i < StringLen(hexStr); i++)
    {
        result *= 16;
        ushort ch = StringGetCharacter(hexStr, i);
        
        if(ch >= '0' && ch <= '9')
            result += ch - '0';
        else if(ch >= 'A' && ch <= 'F')
            result += ch - 'A' + 10;
    }
    
    return result;
}

//+------------------------------------------------------------------+
//| Get timeframe string                                              |
//+------------------------------------------------------------------+
string GetTimeframeString(ENUM_TIMEFRAMES tf)
{
    switch(tf)
    {
        case PERIOD_M1:  return "M1";
        case PERIOD_M5:  return "M5";
        case PERIOD_M15: return "M15";
        case PERIOD_M30: return "M30";
        case PERIOD_H1:  return "H1";
        case PERIOD_H4:  return "H4";
        case PERIOD_D1:  return "D1";
        case PERIOD_W1:  return "W1";
        case PERIOD_MN1: return "MN1";
        default:         return "M30";
    }
}
//+------------------------------------------------------------------+
