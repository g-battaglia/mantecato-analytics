
import { memo, useMemo } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
} from "react-simple-maps";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const GEO_URL =
  "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

/**
 * ISO 3166-1 alpha-2 → ISO 3166-1 numeric mapping.
 * Umami stores country as 2-letter code; TopoJSON uses numeric IDs.
 */
const ALPHA2_TO_NUMERIC: Record<string, string> = {
  AF: "004", AL: "008", DZ: "012", AS: "016", AD: "020", AO: "024",
  AG: "028", AR: "032", AM: "051", AU: "036", AT: "040", AZ: "031",
  BS: "044", BH: "048", BD: "050", BB: "052", BY: "112", BE: "056",
  BZ: "084", BJ: "204", BM: "060", BT: "064", BO: "068", BA: "070",
  BW: "072", BR: "076", BN: "096", BG: "100", BF: "854", BI: "108",
  KH: "116", CM: "120", CA: "124", CV: "132", CF: "140", TD: "148",
  CL: "152", CN: "156", CO: "170", KM: "174", CG: "178", CD: "180",
  CR: "188", CI: "384", HR: "191", CU: "192", CY: "196", CZ: "203",
  DK: "208", DJ: "262", DM: "212", DO: "214", EC: "218", EG: "818",
  SV: "222", GQ: "226", ER: "232", EE: "233", SZ: "748", ET: "231",
  FJ: "242", FI: "246", FR: "250", GA: "266", GM: "270", GE: "268",
  DE: "276", GH: "288", GR: "300", GD: "308", GT: "320", GN: "324",
  GW: "624", GY: "328", HT: "332", HN: "340", HU: "348", IS: "352",
  IN: "356", ID: "360", IR: "364", IQ: "368", IE: "372", IL: "376",
  IT: "380", JM: "388", JP: "392", JO: "400", KZ: "398", KE: "404",
  KI: "296", KP: "408", KR: "410", KW: "414", KG: "417", LA: "418",
  LV: "428", LB: "422", LS: "426", LR: "430", LY: "434", LI: "438",
  LT: "440", LU: "442", MG: "450", MW: "454", MY: "458", MV: "462",
  ML: "466", MT: "470", MH: "584", MR: "478", MU: "480", MX: "484",
  FM: "583", MD: "498", MC: "492", MN: "496", ME: "499", MA: "504",
  MZ: "508", MM: "104", NA: "516", NR: "520", NP: "524", NL: "528",
  NZ: "554", NI: "558", NE: "562", NG: "566", MK: "807", NO: "578",
  OM: "512", PK: "586", PW: "585", PA: "591", PG: "598", PY: "600",
  PE: "604", PH: "608", PL: "616", PT: "620", QA: "634", RO: "642",
  RU: "643", RW: "646", KN: "659", LC: "662", VC: "670", WS: "882",
  SM: "674", ST: "678", SA: "682", SN: "686", RS: "688", SC: "690",
  SL: "694", SG: "702", SK: "703", SI: "705", SB: "090", SO: "706",
  ZA: "710", SS: "728", ES: "724", LK: "144", SD: "729", SR: "740",
  SE: "752", CH: "756", SY: "760", TW: "158", TJ: "762", TZ: "834",
  TH: "764", TL: "626", TG: "768", TO: "776", TT: "780", TN: "788",
  TR: "792", TM: "795", TV: "798", UG: "800", UA: "804", AE: "784",
  GB: "826", US: "840", UY: "858", UZ: "860", VU: "548", VE: "862",
  VN: "704", YE: "887", ZM: "894", ZW: "716",
  XK: "383", PS: "275", HK: "344", MO: "446", PR: "630",
  GL: "304", NC: "540", PF: "258", GU: "316", VI: "850",
};

interface WorldMapProps {
  data: Array<{ country: string; visitors: number }>;
  height?: number;
  onCountryClick?: (countryCode: string) => void;
}

function WorldMapInner({ data, height = 400, onCountryClick }: WorldMapProps) {
  const { countryMap, maxVisitors } = useMemo(() => {
    const map = new Map<string, { visitors: number; code: string }>();
    let max = 0;
    for (const row of data) {
      const numericId = ALPHA2_TO_NUMERIC[row.country];
      if (numericId) {
        map.set(numericId, { visitors: row.visitors, code: row.country });
        if (row.visitors > max) max = row.visitors;
      }
    }
    return { countryMap: map, maxVisitors: max };
  }, [data]);

  function getColor(numericId: string): string {
    const entry = countryMap.get(numericId);
    if (!entry || maxVisitors === 0) return "var(--color-muted)";
    const ratio = Math.log(entry.visitors + 1) / Math.log(maxVisitors + 1);
    const clamped = Math.max(0.08, Math.min(1, ratio));
    return `hsl(221 83% 53% / ${clamped})`;
  }

  // Use a wide aspect ratio: 800×420 matches natural world map proportions
  const svgW = 800;
  const svgH = 420;

  return (
    <TooltipProvider delayDuration={0}>
      <ComposableMap
        projectionConfig={{
          rotate: [-10, 0, 0],
          scale: 155,
        }}
        width={svgW}
        height={svgH}
        style={{ width: "100%", height }}
      >
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const numericId = geo.id;
              const entry = countryMap.get(numericId);
              const fill = getColor(numericId);

              return (
                <Tooltip key={geo.rsmKey}>
                  <TooltipTrigger asChild>
                    <Geography
                      geography={geo}
                      fill={fill}
                      stroke="var(--color-border)"
                      strokeWidth={0.4}
                      onClick={() => {
                        if (entry && onCountryClick) {
                          onCountryClick(entry.code);
                        }
                      }}
                      style={{
                        default: { outline: "none", cursor: entry ? "pointer" : "default" },
                        hover: {
                          outline: "none",
                          fill: entry
                            ? "hsl(221 83% 43%)"
                            : "var(--color-accent)",
                          cursor: entry ? "pointer" : "default",
                        },
                        pressed: { outline: "none" },
                      }}
                    />
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-xs">
                    <span className="font-medium">
                      {geo.properties.name}
                    </span>
                    {entry ? (
                      <span className="ml-1.5 tabular-nums">
                        {entry.visitors.toLocaleString()} visitors
                      </span>
                    ) : (
                      <span className="ml-1.5 text-muted-foreground">
                        No data
                      </span>
                    )}
                  </TooltipContent>
                </Tooltip>
              );
            })
          }
        </Geographies>
      </ComposableMap>
    </TooltipProvider>
  );
}

export const WorldMap = memo(WorldMapInner);
