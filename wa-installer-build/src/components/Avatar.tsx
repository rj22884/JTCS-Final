import { cn } from "@/lib/cn";
import { avatarColor, initials } from "@/lib/format";

export function Avatar({
  name,
  size = 48,
  className,
  src,
}: {
  name: string;
  size?: number;
  className?: string;
  src?: string | null;
}) {
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt=""
        width={size}
        height={size}
        className={cn("inline-block shrink-0 rounded-full object-cover", className)}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={cn("inline-grid shrink-0 place-items-center rounded-full font-medium text-white", className)}
      style={{ width: size, height: size, backgroundColor: avatarColor(name), fontSize: size < 40 ? 12 : 16 }}
    >
      {initials(name)}
    </span>
  );
}
