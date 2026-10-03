interface LogoQProps {
  size?: number;
  className?: string;
}

/**
 * Symbole QUANTA — un Q traité comme un artefact mathématique :
 * un anneau entaillé (évocation de l'ensemble vide ∅) traversé par un
 * vecteur qui se détache et se termine par un point (élément).
 * Ultra-minimal, trait fin, or.
 */
export function LogoQ({ size = 28, className = "" }: LogoQProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden
      className={className}
    >
      <defs>
        <linearGradient
          id="quanta-q-grad"
          x1="10"
          y1="8"
          x2="40"
          y2="44"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#E8D5A3" />
          <stop offset="1" stopColor="#C9A84C" />
        </linearGradient>
      </defs>
      {/* Anneau entaillé */}
      <path
        d="M 35.5 30 A 14 14 0 1 0 26.4 35.8"
        stroke="url(#quanta-q-grad)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      {/* Vecteur */}
      <line
        x1="26.2"
        y1="25.4"
        x2="36"
        y2="40.5"
        stroke="url(#quanta-q-grad)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      {/* Point terminal */}
      <circle cx="37.6" cy="42.8" r="1.9" fill="#E8D5A3" />
    </svg>
  );
}
