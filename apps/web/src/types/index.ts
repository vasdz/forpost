export type RiskCategory =
  | 'sensor_failure'
  | 'fire_risk'
  | 'unauthorized_access'
  | 'infrastructure_wear';

export type RiskDistrict = 'rek-1' | 'rek-2' | 'rek-3' | 'rek-4';

export type SecurityRole = 'dispatcher' | 'chief_engineer' | 'auditor' | 'admin';

export type MaintenancePriority = 'low' | 'medium' | 'high' | 'critical';

export type MaintenanceStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'completed';

export interface RiskPrediction {
  prediction_id: string;
  target_id: string;
  category: RiskCategory;
  probability: number;
  horizon_hours: number;
  calculated_at: string;
  model_version: string;
  explanation: string;
}

export interface MaintenanceOrder {
  order_id: string;
  target_id: string;
  district: string;
  risk_category: RiskCategory;
  priority: MaintenancePriority;
  status: MaintenanceStatus;
  recommended_action: string;
  normative_ref: string;
  deadline_hours: number;
  created_at: string;
  generated_by_model_version: string;
}

export interface MaintenanceGenerationResponse {
  generated_count: number;
  orders: MaintenanceOrder[];
  audit_trail_id: string;
}

export interface AuditVerifyResponse {
  status: 'verified' | 'tampered';
  total_records: number;
  chain_intact: boolean;
}

export interface SecurityContext {
  userId: string;
  label: string;
  role: SecurityRole;
  districts: string[];
}
