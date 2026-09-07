import { InfoIcon } from "./icons";

// Hover/focus tooltip with plain-language explanations.
export default function Tooltip({ text, children, className }) {
  if (!text) return children;
  return (
    <span className={`tooltip-wrap ${className || ""}`} tabIndex={0}>
      {children}
      <span className="tooltip-bubble" role="tooltip">
        {text}
      </span>
    </span>
  );
}

// Small "ⓘ" marker next to a label; hovering shows the explanation.
export function InfoHint({ text }) {
  return (
    <Tooltip text={text}>
      <span className="inline-flex text-gray-400 hover:text-gray-600 cursor-help text-sm">
        <InfoIcon />
      </span>
    </Tooltip>
  );
}