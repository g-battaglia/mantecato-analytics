import { createContext } from "react";
import type { Tracker } from "@mantecato/tracker";

export const TrackerContext = createContext<Tracker | null>(null);
