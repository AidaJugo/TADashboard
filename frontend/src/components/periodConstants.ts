/**
 * Period navigation constants — exported separately so react-refresh
 * fast-reload works correctly (react-refresh/only-export-components).
 */

export type PeriodGroup = "monthly" | "quarterly" | "halfyear" | "annual";

export const PERIOD_GROUPS: Record<
  PeriodGroup,
  { label: string; keys: string[]; labels: Record<string, string> }
> = {
  monthly: {
    label: "Monthly",
    keys: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    labels: {
      Jan: "Jan",
      Feb: "Feb",
      Mar: "Mar",
      Apr: "Apr",
      May: "May",
      Jun: "Jun",
      Jul: "Jul",
      Aug: "Aug",
      Sep: "Sep",
      Oct: "Oct",
      Nov: "Nov",
      Dec: "Dec",
    },
  },
  quarterly: {
    label: "Quarterly",
    keys: ["Q1", "Q2", "Q3", "Q4"],
    labels: { Q1: "Q1", Q2: "Q2", Q3: "Q3", Q4: "Q4" },
  },
  halfyear: {
    label: "Half-Year",
    keys: ["H1", "H2"],
    labels: { H1: "H1", H2: "H2" },
  },
  annual: {
    label: "Annual",
    keys: ["Annual"],
    labels: { Annual: "Annual" },
  },
};
