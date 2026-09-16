/**
 * KeyCustodySuggestionCard
 *
 * Non-custodial key-custody provider suggestion, shown inside the
 * Successor Instructions section of Settings/Trust Roles (People tab).
 *
 * Design intent (approved mockup 2026-09-16, TrustOfficeApp/frontend/mockups/trust-roles-key-custody.html):
 *  - TrustOffice never stores private keys / seed phrases — this card only
 *    POINTS to dedicated custody providers. No keys, no custody, no liability.
 *  - Three options (not one) to preserve TrustOffice's neutral positioning:
 *    My-Legacy.ai (guardian key shares, identity-verified release), Vault12
 *    (encrypted shards to chosen guardians), Casa (multisig vaults).
 *  - "Sponsored" rel + FTC disclosure line — required once affiliate links land.
 *  - Swap link hrefs to affiliate URLs when partner deals close; no other change.
 */
import { ExternalLink } from 'lucide-react';

const PROVIDERS = [
  {
    id: 'my-legacy',
    name: 'My-Legacy.ai',
    logo: `${process.env.PUBLIC_URL}/assets/partners/my-legacy.png`,
    url: 'https://my-legacy.ai/',
    desc: 'Splits your seed phrase into key shares held by guardians; released only to your identity-verified successor.',
  },
  {
    id: 'vault12',
    name: 'Vault12',
    logo: `${process.env.PUBLIC_URL}/assets/partners/vault12.png`,
    url: 'https://vault12.com/',
    desc: 'Encrypted key shards distributed across guardians you choose — non-custodial backup and inheritance.',
  },
  {
    id: 'casa',
    name: 'Casa',
    logo: `${process.env.PUBLIC_URL}/assets/partners/casa.png`,
    url: 'https://casa.io/inheritance',
    desc: 'Multisig vaults with inheritance planning included in every membership. Best known for Bitcoin.',
  },
];

export default function KeyCustodySuggestionCard() {
  return (
    <div
      className="mt-6 p-6 bg-[#F5F5F7] border border-navy/20"
      data-testid="key-custody-suggestion"
    >
      <span className="inline-flex items-center gap-1.5 border border-gold/50 bg-gold/5 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.2em] text-gold">
        Suggestion — Key Custody
      </span>
      <h3 className="font-serif text-xl text-navy mt-3 mb-2.5">
        Where will your digital keys live?
      </h3>
      <p className="text-sm text-slate-600 leading-relaxed mb-4">
        TrustOffice never stores private keys, seed phrases, or wallet credentials — by design. If this
        trust holds self-custody crypto or other digital assets, use a dedicated{' '}
        <b className="text-navy">key-custody service</b> to store and release them securely, then record
        the arrangement (provider, guardians, release conditions) in your Letter of Guidance so your
        successor trustee knows exactly where to go.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        {PROVIDERS.map((p) => (
          <a
            key={p.id}
            href={p.url}
            target="_blank"
            rel="noopener sponsored"
            data-testid={`custody-provider-${p.id}`}
            className="block bg-white border border-navy/20 p-3.5 hover:border-gold transition-colors"
          >
            <img src={p.logo} alt={`${p.name} logo`} className="w-9 h-9 mb-2.5" />
            <div className="font-serif text-base font-semibold text-navy flex items-center gap-1.5 mb-1">
              {p.name}
              <ExternalLink className="w-2.5 h-2.5 text-slate-400" />
            </div>
            <div className="text-[11.5px] leading-snug text-muted-foreground">{p.desc}</div>
          </a>
        ))}
      </div>

      <p className="text-[11px] text-slate-400 leading-relaxed border-t border-navy/10 pt-3">
        TrustOffice may receive a commission if you sign up through these links. TrustOffice provides
        governance software only — it does not hold keys, provide custody, and is not affiliated with
        these providers.
      </p>
    </div>
  );
}