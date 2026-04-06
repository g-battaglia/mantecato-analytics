import { useEffect, useRef, useMemo } from "react";
import { createTracker, type TrackerConfig } from "@mantecato/tracker";
import { TrackerContext } from "./TrackerContext";

export interface TrackerProviderProps extends TrackerConfig {
  children: React.ReactNode;
}

export function TrackerProvider({ children, ...config }: TrackerProviderProps) {
  const configRef = useRef(config);
  configRef.current = config;

  const tracker = useMemo(
    () => createTracker(configRef.current),
    // Only recreate if websiteId or baseUrl change
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [config.websiteId, config.baseUrl],
  );

  useEffect(() => {
    return () => {
      tracker.destroy();
    };
  }, [tracker]);

  return (
    <TrackerContext.Provider value={tracker}>
      {children}
    </TrackerContext.Provider>
  );
}
