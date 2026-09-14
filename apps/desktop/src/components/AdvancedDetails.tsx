import { useState } from "react";
import { AppIcon } from "./AppIcon";

interface AdvancedDetailsProps {
  children: React.ReactNode;
}

export function AdvancedDetails({ children }: AdvancedDetailsProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <details className="advanced-details" open={isOpen} onToggle={(e) => setIsOpen(e.currentTarget.open)}>
      <summary className="advanced-details-summary">
        <AppIcon name="document" size={16} />
        <span>Advanced technical details</span>
      </summary>
      <div className="advanced-details-content">
        {children}
      </div>
    </details>
  );
}
