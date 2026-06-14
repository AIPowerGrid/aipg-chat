// Whitelabel: AI Power Grid logo (replaces default Onyx typed logo).
interface OnyxLogoTypedProps { size?: number; className?: string; }
const SvgOnyxLogoTyped = ({ size, className }: OnyxLogoTypedProps) => (
  // eslint-disable-next-line @next/next/no-img-element
  <img
    src="/aipg-logo.svg"
    alt="AI Power Grid"
    className={className}
    style={{ height: size, objectFit: "contain" }}
  />
);
export default SvgOnyxLogoTyped;
