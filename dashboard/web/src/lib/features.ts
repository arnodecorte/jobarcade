import { createContext, useContext } from "react";

const SCRAPER_ONLY = new Set(["fresh", "discover"]);

/** Hide the routes that only make sense when URL scraping is enabled. */
export function visibleNav<T extends { key: string }>(items: T[], scraper: boolean): T[] {
  return scraper ? items : items.filter((i) => !SCRAPER_ONLY.has(i.key));
}

/** Whether the experimental URL-scraping feature is on (defaults to off). */
export const ScraperContext = createContext<boolean>(false);
export const useScraperEnabled = () => useContext(ScraperContext);
