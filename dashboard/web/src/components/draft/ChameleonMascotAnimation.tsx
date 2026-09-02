type Props = {
  compact?: boolean;
};

export function ChameleonMascotAnimation({ compact = false }: Props) {
  return (
    <div className={compact ? "chameleon-mascot compact" : "chameleon-mascot"} aria-hidden="true">
      <div className="chameleon-stage">
        <div className="chameleon-sprite" />
      </div>
    </div>
  );
}
