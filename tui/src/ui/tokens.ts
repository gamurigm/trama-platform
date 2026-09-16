export const colors = {
  void: "#07111F",
  panel: "#10253A",
  text: "#E8F1F8",
  focus: "#63E6E2",
  cognitive: "#B8A1FF",
  attention: "#FFB454",
  danger: "#F07178",
  muted: "#7890A5",
} as const;

export const spacing = {
  panel: 1,
  section: 1,
  inline: 1,
} as const;

export const borders = {
  style: "single" as const,
} as const;

export const density = {
  compact: 1,
  relaxed: 2,
} as const;

export type Accent = "focus" | "cognitive" | "attention" | "danger" | "muted";
