export interface PanelModuleConfig {
  id: string;
  name: string;
  enabled: boolean;
  order: number;
  props?: Record<string, unknown>;
}

export interface PanelLayoutConfig {
  defaultPeriod?: string;
  showRankPeriodSelector?: boolean;
  [key: string]: unknown;
}

export interface PanelConfig {
  modules: PanelModuleConfig[];
  layout: PanelLayoutConfig;
}
