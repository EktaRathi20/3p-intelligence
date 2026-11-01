import type { FC } from 'react';
import { RescueCommandCentre, type RescueCommandCentreProps } from '@/components/dashboard/rescue/RescueCommandCentre';

interface LandfallRescueModeViewProps extends RescueCommandCentreProps {
  isLightMode?: boolean;
}

/**
 * Rescue & Relief Operations entry point (route `/landfall`).
 * Renders the Emergency Response Command Centre; the legacy chatbot-only
 * layout lives on as the integrated AI Tactical Assistant panel.
 */
export const LandfallRescueModeView: FC<LandfallRescueModeViewProps> = (props) => (
  <RescueCommandCentre {...props} />
);
