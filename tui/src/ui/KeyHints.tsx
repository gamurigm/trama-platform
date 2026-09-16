type KeyHint = { key: string; label: string };

export function KeyHints({ items }: { items: KeyHint[] }) {
  return (
    <text wrapMode="none">
      {items.map((item, index) => (
        <span key={item.key}>
          {index > 0 ? "  " : ""}
          <strong fg="#63E6E2">[{item.key}]</strong> {item.label}
        </span>
      ))}
    </text>
  );
}
