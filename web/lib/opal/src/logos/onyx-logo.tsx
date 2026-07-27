// Whitelabel: AI Power Grid mark (replaces default Onyx logo).
const SvgOnyxLogo = ({ size, className }: { size?: number; className?: string }) => (
  // eslint-disable-next-line @next/next/no-img-element
  <img
    src="/aipg-logo.svg"
    alt="AI Power Grid"
    className={className}
    style={{ height: size, width: size, objectFit: "contain" }}
  />
);
export default SvgOnyxLogo;
