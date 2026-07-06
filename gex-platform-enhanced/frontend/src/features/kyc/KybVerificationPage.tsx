/**
 * KybVerification — Know Your Business flow.
 *
 * Triggered automatically after KYC for real (OAuth/email) users when they
 * declared a company. The user can either:
 *   (a) fill the KYB themselves (if they are the responsible person), or
 *   (b) delegate it to a colleague — the colleague will be routed through
 *       the same KYB flow when they sign in (or sign up) with that email.
 *
 * Demo / credential accounts are exempt and never see this page.
 *
 * @route /kyb
 */
import brandIcon from "@/assets/greenearthx-icon.png";
import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Building2, User, Mail, ArrowRight, ChevronLeft,
  CheckCircle2, Shield, Send, UserCheck, Briefcase,
} from "lucide-react";
import {
  useKycState,
  inviteColleagueForKyb,
  getKybInvitationFor,
  consumeKybInvitation,
} from "./kycState";

type Step = "intent" | "self-form" | "delegate" | "delegate-sent" | "done";

const KybVerification = () => {
  const navigate = useNavigate();
  const kyc = useKycState();
  const kycEmail = kyc.kycProfile?.companyEmail || "";

  const incomingInvite = useMemo(() => getKybInvitationFor(kycEmail), [kycEmail]);

  const [step, setStep] = useState<Step>(
    incomingInvite ? "self-form" : "intent"
  );

  // KYB business form
  const company = kyc.company || incomingInvite?.companyName || kyc.kycProfile?.companyName || "";
  const [legalName, setLegalName] = useState(company);
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [country, setCountry] = useState(kyc.kycProfile?.country || "");
  const [vatId, setVatId] = useState("");
  const [registeredAddress, setRegisteredAddress] = useState("");
  const [beneficialOwners, setBeneficialOwners] = useState("");
  const [responsibleName, setResponsibleName] = useState("");
  const [responsibleEmail, setResponsibleEmail] = useState(kycEmail);
  const [responsibleJobTitle, setResponsibleJobTitle] = useState(kyc.kycProfile?.jobTitle || "");

  // Delegation form
  const userDomain = kycEmail.split("@")[1] || "";
  const [colName, setColName] = useState("");
  const [colEmail, setColEmail] = useState("");
  const [colJob, setColJob] = useState("");

  const inputCls = "mt-1 h-10 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring";
  const labelCls = "text-xs font-semibold text-card-foreground";
  const btnPrimary = "inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50";
  const btnSecondary = "inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground";

  const canSubmitSelf =
    legalName.trim() && registrationNumber.trim() && country.trim() &&
    registeredAddress.trim() && responsibleName.trim() && responsibleEmail.includes("@");

  const canDelegate =
    colName.trim() && colEmail.includes("@") &&
    (!userDomain || colEmail.toLowerCase().endsWith(`@${userDomain.toLowerCase()}`));

  const submitSelf = () => {
    kyc.setKybCompleted({
      legalName, registrationNumber, country, vatId, registeredAddress,
      beneficialOwners, responsibleName, responsibleEmail, responsibleJobTitle,
    });
    if (incomingInvite && kycEmail) consumeKybInvitation(kycEmail);
    setStep("done");
  };

  const submitDelegation = () => {
    inviteColleagueForKyb({
      email: colEmail.trim().toLowerCase(),
      companyName: company || legalName,
      companyDomain: userDomain,
      invitedBy: kycEmail,
      invitedByName: kyc.kycProfile?.firstName || "",
      createdAt: new Date().toISOString(),
    });
    kyc.setKybStatus("pending_colleague");
    setStep("delegate-sent");
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-white/10 px-6 py-3" style={{ background: "linear-gradient(135deg, hsl(200 25% 10%), hsl(174 45% 18%))" }}>
        <div className="mx-auto max-w-2xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src={brandIcon} alt="GreenEarthX" className="h-8 w-auto" />
            <div className="h-5 w-px bg-white/20" />
            <div>
              <h1 className="font-display text-sm font-bold text-white tracking-tight">Business Verification (KYB)</h1>
              <p className="text-[10px] text-white/50">{company || "Organisation"}</p>
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-2xl px-6 py-8">
        {/* INTENT */}
        {step === "intent" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">Verify your organisation</h2>
              <p className="text-sm text-muted-foreground">
                You declared <span className="font-semibold text-card-foreground">{company || "your company"}</span> during identity verification.
                We now need to verify the business itself. A person from {company || "the organisation"} must complete this step.
              </p>
            </div>

            <div className="grid gap-3">
              <button
                onClick={() => setStep("self-form")}
                className="text-left rounded-xl border-2 border-border hover:border-primary/40 hover:bg-accent/30 p-4 transition-all"
              >
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <UserCheck className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-card-foreground">I am the responsible person</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Fill in the company registration, address, ownership and authorised representative details now.
                    </p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => setStep("delegate")}
                className="text-left rounded-xl border-2 border-border hover:border-primary/40 hover:bg-accent/30 p-4 transition-all"
              >
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                    <Send className="h-5 w-5 text-amber-500" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-card-foreground">Invite a colleague to complete it</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      We'll email a colleague (compliance / legal / finance) and route them through the same KYB when they sign in.
                    </p>
                  </div>
                </div>
              </button>
            </div>

            <div className="rounded-lg bg-primary/5 border border-primary/10 px-4 py-3">
              <p className="text-xs text-primary flex items-start gap-2">
                <Shield className="h-4 w-4 flex-shrink-0 mt-0.5" />
                Once your organisation is verified, every colleague signing in with an <span className="font-mono">@{userDomain}</span> address skips this step automatically.
              </p>
            </div>
          </div>
        )}

        {/* SELF FORM */}
        {step === "self-form" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            {incomingInvite && (
              <div className="rounded-lg bg-amber-500/5 border border-amber-500/20 px-4 py-3">
                <p className="text-xs text-card-foreground flex items-start gap-2">
                  <Mail className="h-4 w-4 flex-shrink-0 mt-0.5 text-amber-500" />
                  <span>
                    <strong>{incomingInvite.invitedByName || incomingInvite.invitedBy}</strong> invited you to complete the business verification for <strong>{incomingInvite.companyName}</strong>.
                  </span>
                </p>
              </div>
            )}

            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">Company details</h2>
              <p className="text-sm text-muted-foreground">
                These details will be cross-referenced against business registries.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className={labelCls}>Legal Company Name *</label>
                <div className="relative mt-1">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input value={legalName} onChange={(e) => setLegalName(e.target.value)} className={`${inputCls} pl-10`} />
                </div>
              </div>
              <div>
                <label className={labelCls}>Registration Number *</label>
                <input value={registrationNumber} onChange={(e) => setRegistrationNumber(e.target.value)} placeholder="e.g. KvK 24123456" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Country of Registration *</label>
                <input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Netherlands" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>VAT / Tax ID</label>
                <input value={vatId} onChange={(e) => setVatId(e.target.value)} placeholder="NL123456789B01" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Registered Address *</label>
                <input value={registeredAddress} onChange={(e) => setRegisteredAddress(e.target.value)} placeholder="Street, City, Postal code" className={inputCls} />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Beneficial Owners (≥25%)</label>
                <textarea value={beneficialOwners} onChange={(e) => setBeneficialOwners(e.target.value)} rows={2} placeholder="Name, % ownership, nationality" className={`${inputCls} h-auto py-2`} />
              </div>
            </div>

            <div className="space-y-1 pt-2">
              <h3 className="text-xs font-bold text-card-foreground uppercase tracking-wider">Authorised Representative</h3>
              <div className="h-px bg-border" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Full Name *</label>
                <input value={responsibleName} onChange={(e) => setResponsibleName(e.target.value)} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Job Title</label>
                <div className="relative mt-1">
                  <Briefcase className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input value={responsibleJobTitle} onChange={(e) => setResponsibleJobTitle(e.target.value)} placeholder="Chief Compliance Officer" className={`${inputCls} pl-10`} />
                </div>
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Email *</label>
                <div className="relative mt-1">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input value={responsibleEmail} onChange={(e) => setResponsibleEmail(e.target.value)} className={`${inputCls} pl-10`} />
                </div>
              </div>
            </div>

            <div className="flex justify-between">
              {!incomingInvite ? (
                <button onClick={() => setStep("intent")} className={btnSecondary}>
                  <ChevronLeft className="h-4 w-4" /> Back
                </button>
              ) : <span />}
              <button onClick={submitSelf} disabled={!canSubmitSelf} className={btnPrimary}>
                Submit verification <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* DELEGATE */}
        {step === "delegate" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">Invite the responsible colleague</h2>
              <p className="text-sm text-muted-foreground">
                Provide the contact details of the person at {company || "your company"} responsible for legal / compliance.
                They will receive an email and complete the KYB through their own account.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Colleague's Full Name *</label>
                <div className="relative mt-1">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input value={colName} onChange={(e) => setColName(e.target.value)} placeholder="Anna Müller" className={`${inputCls} pl-10`} />
                </div>
              </div>
              <div>
                <label className={labelCls}>Job Title</label>
                <input value={colJob} onChange={(e) => setColJob(e.target.value)} placeholder="Head of Compliance" className={inputCls} />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Company Email *</label>
                <div className="relative mt-1">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input
                    value={colEmail}
                    onChange={(e) => setColEmail(e.target.value)}
                    placeholder={userDomain ? `name@${userDomain}` : "name@company.com"}
                    className={`${inputCls} pl-10`}
                  />
                </div>
                {userDomain && colEmail && !colEmail.toLowerCase().endsWith(`@${userDomain.toLowerCase()}`) && (
                  <p className="text-[10px] text-destructive mt-1">Email must use the same domain (@{userDomain})</p>
                )}
              </div>
            </div>

            <div className="rounded-lg bg-primary/5 border border-primary/10 px-4 py-3">
              <p className="text-xs text-primary flex items-start gap-2">
                <Shield className="h-4 w-4 flex-shrink-0 mt-0.5" />
                If your colleague is not yet registered, they'll be guided through the same sign-in, KYC and KYB journey.
              </p>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep("intent")} className={btnSecondary}>
                <ChevronLeft className="h-4 w-4" /> Back
              </button>
              <button onClick={submitDelegation} disabled={!canDelegate} className={btnPrimary}>
                Send invitation <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* DELEGATE SENT */}
        {step === "delegate-sent" && (
          <div className="bg-card border border-border rounded-xl p-8 text-center space-y-5">
            <div className="mx-auto h-16 w-16 rounded-full bg-amber-500/10 flex items-center justify-center">
              <Send className="h-8 w-8 text-amber-500" />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-bold text-card-foreground">Invitation sent</h2>
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                We've notified <span className="font-semibold text-card-foreground">{colName}</span> at <span className="font-mono">{colEmail}</span>.
                You can keep using the platform with limited access until the business verification is completed.
              </p>
            </div>
            <div className="flex justify-center gap-3">
              <button onClick={() => setStep("intent")} className={btnSecondary}>
                Change responsible person
              </button>
              <button onClick={() => navigate("/")} className={btnPrimary}>
                Continue to platform <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* DONE */}
        {step === "done" && (
          <div className="bg-card border border-border rounded-xl p-8 text-center space-y-5">
            <div className="mx-auto h-16 w-16 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <CheckCircle2 className="h-8 w-8 text-emerald-500" />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-bold text-card-foreground">Business verified</h2>
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                {legalName} is now verified. All colleagues from <span className="font-mono">@{userDomain}</span> will be able to sign in and skip this step.
              </p>
            </div>
            <button onClick={() => navigate("/")} className={btnPrimary}>
              Continue to platform <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export { KybVerification };
export default KybVerification;