import { useOutletContext } from 'react-router-dom';
import { InsuranceRecoveryModeView } from '@/components/dashboard/modes/InsuranceRecoveryModeView';
import type { DashboardOutletData } from '../types/dashboard';
import { isAvailableDisasterIntelligence } from '../types/api';

export default function RecoveryPage() {
  const { selectedCity, activeIntelligence } = useOutletContext<DashboardOutletData>();
  if (!selectedCity) return null;
  const insuranceSummary = isAvailableDisasterIntelligence(activeIntelligence)
    ? activeIntelligence.insurance_summary
    : undefined;

  return (
    <InsuranceRecoveryModeView
      insuranceSummary={insuranceSummary}
      isLightMode
    />
  );
}
