// Screen: Shared component — Login / role-switching screens
import { useState } from 'react';
import { useUserRole } from '@/contexts/UserRoleContext';
import type { CompanyType, ServiceType, BusinessFunction } from '@/contexts/UserRoleContext';

export function RoleSelector({ onComplete }: { onComplete?: () => void }) {
  const { role, setRole } = useUserRole();
  const [companyType, setCompanyType] = useState<CompanyType>(role.company_type);
  const [serviceType, setServiceType] = useState<ServiceType>(role.service_type);
  const [businessFunction, setBusinessFunction] = useState<BusinessFunction>(role.business_function);
  const [companyName, setCompanyName] = useState(role.company_name);
  const [userName, setUserName] = useState(role.user_name);

  const COMPANY_TYPES: { value: CompanyType; label: string; desc: string }[] = [
    { value: 'PRODUCER', label: 'Producer', desc: 'We produce GreenEarthX molecules (e-Methane, e-Methanol, e-NH3, HVO, SAF, e-Gasoline, e-LG, e-Naphtha)' },
    { value: 'OFFTAKER', label: 'Offtaker / Buyer', desc: 'We buy or offtake green fuel molecules' },
    { value: 'THIRD_PARTY', label: 'Service Provider', desc: 'We provide services to producers or offtakers' },
  ];

  const SERVICE_TYPES: { value: ServiceType; label: string }[] = [
    { value: 'BANK', label: 'Banking / Lending' },
    { value: 'INSURER', label: 'Insurance / Risk' },
    { value: 'CERTIFIER', label: 'Certification / Audit' },
    { value: 'LOGISTICS', label: 'Logistics / Shipping' },
    { value: 'ENGINEER', label: 'Engineering / IE' },
    { value: 'EQUIPMENT', label: 'Equipment / OEM' },
    { value: 'LEGAL', label: 'Legal / Advisory' },
  ];

  const FUNCTIONS: { value: BusinessFunction; label: string }[] = [
    { value: 'ENGINEERING', label: 'Engineering & Technical' },
    { value: 'FINANCE_TREASURY', label: 'Finance & Treasury' },
    { value: 'COMMERCIAL', label: 'Commercial & Sales' },
    { value: 'COMPLIANCE_LEGAL', label: 'Compliance, Legal & Regulation' },
    { value: 'OPERATIONS', label: 'Operations' },
    { value: 'EXECUTIVE', label: 'Executive / Management' },
  ];

  const handleSave = () => {
    setRole({
      company_type: companyType,
      service_type: companyType === 'THIRD_PARTY' ? serviceType : null,
      business_function: businessFunction,
      company_name: companyName,
      user_name: userName,
    });
    onComplete?.();
  };

  const radioGroupClass = 'grid grid-cols-1 gap-2 mt-2';
  const radioClass = (selected: boolean) =>
    `flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
      selected
        ? 'border-teal-500 bg-teal-900/20 text-white'
        : 'border-gray-700 bg-gray-900/50 text-gray-400 hover:border-gray-600'
    }`;

  return (
    <div className="max-w-lg mx-auto space-y-6">
      {/* Company name + user name */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">Company</label>
          <input
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            className="mt-1 w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-gray-200"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">Your Name</label>
          <input
            value={userName}
            onChange={(e) => setUserName(e.target.value)}
            className="mt-1 w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-gray-200"
          />
        </div>
      </div>

      {/* 1. Company type */}
      <div>
        <label className="text-xs text-gray-500 uppercase tracking-wider">
          What does your company do?
        </label>
        <div className={radioGroupClass}>
          {COMPANY_TYPES.map((ct) => (
            <div
              key={ct.value}
              onClick={() => setCompanyType(ct.value)}
              className={radioClass(companyType === ct.value)}
            >
              <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex-shrink-0 ${
                companyType === ct.value ? 'border-teal-500 bg-teal-500' : 'border-gray-600'
              }`} />
              <div>
                <p className="text-sm font-medium">{ct.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{ct.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. Service type (if third-party) */}
      {companyType === 'THIRD_PARTY' && (
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">
            What service do you provide?
          </label>
          <div className="grid grid-cols-2 gap-2 mt-2">
            {SERVICE_TYPES.map((st) => (
              <div
                key={String(st.value)}
                onClick={() => setServiceType(st.value)}
                className={radioClass(serviceType === st.value)}
              >
                <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex-shrink-0 ${
                  serviceType === st.value ? 'border-teal-500 bg-teal-500' : 'border-gray-600'
                }`} />
                <p className="text-sm">{st.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Business function */}
      <div>
        <label className="text-xs text-gray-500 uppercase tracking-wider">
          Your primary business function
        </label>
        <div className={radioGroupClass}>
          {FUNCTIONS.map((fn) => (
            <div
              key={fn.value}
              onClick={() => setBusinessFunction(fn.value)}
              className={radioClass(businessFunction === fn.value)}
            >
              <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex-shrink-0 ${
                businessFunction === fn.value ? 'border-teal-500 bg-teal-500' : 'border-gray-600'
              }`} />
              <p className="text-sm">{fn.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Save */}
      <button
        onClick={handleSave}
        className="w-full py-3 rounded-lg bg-teal-600 hover:bg-teal-500 text-white font-medium transition-colors"
      >
        Continue →
      </button>
    </div>
  );
}
