/** What `ActionPanel.previewing()` spreads onto a control that names a card. */
export interface PreviewProps {
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onFocus?: () => void;
  onBlur?: () => void;
  "data-preview-oid"?: number;
}

export type Previewing = (oid: number | null | undefined) => PreviewProps;
