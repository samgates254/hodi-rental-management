import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="hodi-section-label">
      <span aria-hidden="true" />
      {children}
    </p>
  );
}

function PreviewBar({ title }: { title: string }) {
  return (
    <div className="hodi-preview-bar">
      <span className="hodi-window-dots" aria-hidden="true"><i /><i /><i /></span>
      <span>{title}</span>
      <span>Illustrative preview</span>
    </div>
  );
}

function DashboardPreview() {
  return (
    <div className="hodi-dashboard-preview" aria-label="Illustrative HODI landlord workspace preview">
      <PreviewBar title="HODI / LANDLORD WORKSPACE" />
      <div className="hodi-dashboard-body">
        <aside className="hodi-dashboard-sidebar" aria-label="Illustrative workspace navigation">
          <span className="hodi-dashboard-brand">HODI</span>
          <span className="is-current">Overview</span>
          <span>Properties</span>
          <span>Rent</span>
          <span>Maintenance</span>
          <span>Utilities</span>
          <span>Tenants</span>
        </aside>
        <div className="hodi-dashboard-content">
          <div className="hodi-dashboard-topline"><span>Overview</span><span>Workspace setup</span></div>
          <div className="hodi-dashboard-welcome">
            <div><p>YOUR WORKSPACE</p><h3>An organised home for<br className="hidden sm:block" /> your property records.</h3></div>
            <span className="hodi-preview-action">Add a property</span>
          </div>
          <div className="hodi-preview-stats">
            <div><span>Properties</span><strong>Ready when you are</strong></div>
            <div><span>Rent records</span><strong>Awaiting setup</strong></div>
            <div><span>Maintenance</span><strong>No requests yet</strong></div>
          </div>
          <div className="hodi-dashboard-empty">
            <div><p>YOUR FIRST STEPS</p><strong>Make room for a simpler day.</strong><span>Add property details to begin organising your workspace.</span></div>
            <ul><li>Add your property details</li><li>Create units and tenant records</li><li>Set up rent and utility records</li></ul>
          </div>
          <p className="hodi-preview-footnote">ACTIVITY · EMPTY-STATE PREVIEW</p>
        </div>
      </div>
    </div>
  );
}

function RentPreview() {
  return (
    <div className="hodi-rent-preview" aria-label="Illustrative rent workspace with no records entered">
      <div className="hodi-mini-window-head"><span>Rent records</span><span>Statements&nbsp;&nbsp; Reminders</span></div>
      <div className="hodi-table-head"><span>UNIT / TENANT</span><span>RENT AMOUNT</span><span>RECORD STATUS</span></div>
      <div className="hodi-table-empty"><span>No tenant assigned</span><strong>KES —</strong><span>Not configured</span></div>
      <p>Illustrative rent workspace. Amounts and records appear after setup; no payment activity is shown.</p>
    </div>
  );
}

function UtilitiesPreview() {
  return (
    <div className="hodi-utilities-preview" aria-label="Illustrative utility records with no readings entered">
      <div className="hodi-mini-window-head"><span>Utility records</span><span>ILLUSTRATIVE UI</span></div>
      <div className="hodi-utility-row"><span className="hodi-utility-icon" aria-hidden="true">W</span><span><strong>Water</strong><small>No readings added</small></span><b>—</b></div>
      <div className="hodi-utility-row"><span className="hodi-utility-icon" aria-hidden="true">E</span><span><strong>Electricity</strong><small>No records added</small></span><b>—</b></div>
      <p>Readings and charges appear once you add your records.</p>
    </div>
  );
}

function TenantPreview() {
  return (
    <div className="hodi-tenant-preview" aria-label="Illustrative tenant profile without personal information">
      <div className="hodi-mini-window-head"><span>Your next tenant record.</span><span>ILLUSTRATIVE PROFILE · NOT A REAL TENANT</span></div>
      <div className="hodi-tenant-profile"><span className="hodi-profile-mark" aria-hidden="true">—</span><div><small>TENANT RECORD</small><strong>Contact details</strong><span>Not added</span></div></div>
      <div className="hodi-tenant-fields"><div><span>Lease information</span><b>Not added</b></div><div><span>Assigned unit</span><b>Not assigned</b></div></div>
      <p>A single record for the practical details, with room for the human ones.</p>
    </div>
  );
}

export function HomepageExperience() {
  return (
    <main id="main" className="hodi-home">
      <section className="hodi-home-hero" aria-labelledby="home-hero-title">
        <div className="hodi-home-hero-copy">
          <SectionLabel>Property management. Thoughtfully connected.</SectionLabel>
          <h1 className="hodi-home-title" id="home-hero-title">Property management, made simpler.</h1>
          <p>Less chasing. More clarity. Bring your properties, rent and everyday responsibilities into one calm workspace, built for Kenya.</p>
          <div className="hodi-home-hero-actions">
            <Button href="/signup?type=landlord" size="lg">Get Started</Button>
            <Button href="#features" variant="outline-light" size="lg">Explore Features</Button>
          </div>
          <Link
            href="/marketplace"
            className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-white underline decoration-white/50 underline-offset-4 hover:decoration-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
          >
            Looking for a home? Browse published listings <span aria-hidden="true">→</span>
          </Link>
          <div className="hodi-hero-signature"><span>For the places you care for.</span><i aria-hidden="true" /></div>
        </div>
        <figure className="hodi-home-hero-visual">
          <Image src="/images/hodi/modern-block.jpg" alt="Modern multi-storey apartment building photographed from above" fill priority sizes="(max-width: 800px) 100vw, 55vw" className="hodi-home-hero-image" />
          <figcaption><span>Property, tenancy and everyday work in one record.</span><small>ILLUSTRATIVE PHOTOGRAPH</small></figcaption>
        </figure>
      </section>

      <section id="workspace" className="hodi-workspace-section" aria-labelledby="workspace-title">
        <Container>
          <div className="hodi-section-intro">
            <div><SectionLabel>The HODI workspace</SectionLabel><h2 id="workspace-title">A clearer view.<br />A calmer working day.</h2></div>
            <div className="hodi-section-intro-copy"><p>Your portfolio is more than a collection of buildings. Keep the details that matter together, from a tenant’s first day to the next maintenance request.</p><small>Illustrative product preview · Sample empty states, not live account data.</small></div>
          </div>
          <DashboardPreview />
          <div className="hodi-capability-strip" aria-label="Connected workspace capabilities">
            <span>One property workspace</span><span>Rent &amp; utility records</span><span>Maintenance follow-through</span><span>Tenant details, together</span>
          </div>
        </Container>
      </section>

      <section id="features" className="hodi-feature-section hodi-feature-rent" aria-labelledby="rent-title">
        <Container className="hodi-feature-grid">
          <RentPreview />
          <div className="hodi-feature-copy"><SectionLabel>Rent management</SectionLabel><h2 id="rent-title">Every rent detail,<br />in its right place.</h2><p>Replace scattered spreadsheets and follow-ups with an organised record of rent. Know what needs attention without losing sight of the details.</p><ul><li>Keep unit and tenant rent records together</li><li>Review statements and follow-up notes</li><li>Organise amounts in Kenyan shillings</li></ul><a className="hodi-text-link" href="/platform#finance">Explore rent management <span aria-hidden="true">→</span></a></div>
        </Container>
      </section>

      <section className="hodi-feature-section hodi-feature-maintenance" aria-labelledby="maintenance-title">
        <Container className="hodi-feature-grid hodi-feature-reverse">
          <div className="hodi-feature-copy"><SectionLabel>Maintenance &amp; care</SectionLabel><h2 id="maintenance-title">Small issues deserve<br />a clear next step.</h2><p>A repair is easier to manage when the request, the conversation and the follow-through stay connected. Give every issue a place, from first note to resolution.</p><ul><li>Capture requests with the right context</li><li>Keep updates against the relevant property</li><li>Follow progress in one shared record</li></ul><a className="hodi-text-link" href="/platform#maintenance">Explore maintenance <span aria-hidden="true">→</span></a></div>
          <div className="hodi-maintenance-visual"><Image src="/images/hodi/open-living-dining.jpg" alt="Open-plan living and dining room with a glazed wall" fill sizes="(max-width: 800px) 100vw, 50vw" className="object-cover" /><div className="hodi-request-note"><small>ILLUSTRATIVE REQUEST</small><strong>A place for every repair.</strong><span>Property not selected</span><em>Draft</em><p>Add details and photos to create a clear record.</p></div></div>
        </Container>
      </section>

      <section className="hodi-feature-section hodi-feature-utilities" aria-labelledby="utilities-title">
        <Container className="hodi-feature-grid">
          <UtilitiesPreview />
          <div className="hodi-feature-copy"><SectionLabel>Utility records</SectionLabel><h2 id="utilities-title">Bring the essentials<br />into view.</h2><p>Keep water and electricity records alongside the property they belong to. Readings, charges and notes become easier to find, and easier to explain.</p><a className="hodi-text-link" href="/platform#finance">Explore utilities <span aria-hidden="true">→</span></a></div>
        </Container>
      </section>

      <section className="hodi-feature-section hodi-feature-tenants" aria-labelledby="tenants-title">
        <Container className="hodi-feature-grid hodi-feature-reverse">
          <div className="hodi-feature-copy"><SectionLabel>Tenants &amp; relationships</SectionLabel><h2 id="tenants-title">Good management<br />starts with people.</h2><p>Keep tenant details, lease information and important notes in one place. Spend less time searching for a record and more time taking care of the relationship.</p><a className="hodi-text-link" href="/platform#tenancy">Explore tenant management <span aria-hidden="true">→</span></a></div>
          <TenantPreview />
        </Container>
      </section>

      <section className="hodi-properties-section" aria-labelledby="properties-title">
        <Container>
          <div className="hodi-properties-heading"><div><SectionLabel>Spaces, connected</SectionLabel><h2 id="properties-title">Different properties.<br />The same thoughtful approach.</h2></div><p>From a single home to a growing portfolio, bring the everyday work of property management together.</p></div>
          <div className="hodi-property-gallery">
            <article><Image src="/images/hodi/tower-balconies.jpg" alt="White residential tower with stacked balconies" width={451} height={679} sizes="(max-width: 700px) 90vw, 33vw" /><div><strong>Residential towers</strong><span>A record for every unit</span></div></article>
            <article><Image src="/images/hodi/mixed-use-block.jpg" alt="Street-front apartment building with timber balconies" width={460} height={305} sizes="(max-width: 700px) 90vw, 33vw" /><div><strong>Street-front blocks</strong><span>Shared buildings, separate tenancies</span></div></article>
            <article><Image src="/images/hodi/city-balcony-living.jpg" alt="Living room opening onto a city balcony" width={571} height={536} sizes="(max-width: 700px) 90vw, 33vw" /><div><strong>Lived-in homes</strong><span>The rooms people actually use</span></div></article>
          </div>
          <p className="hodi-property-disclaimer">Illustrative property imagery and settings. These are not HODI customer properties or listings; no availability or pricing is represented.</p>
        </Container>
      </section>

      <section id="how-it-works" className="hodi-start-section" aria-labelledby="start-title">
        <Container>
          <div className="hodi-start-heading"><h2 id="start-title">A thoughtful start.<br />A simpler routine.</h2><SectionLabel>Getting started</SectionLabel></div>
          <ol className="hodi-start-steps"><li><span>01</span><h3>Create your workspace</h3><p>Start with a dedicated home for your property records and day-to-day management.</p></li><li><span>02</span><h3>Bring in the details</h3><p>Add properties, units and tenants. Give each practical detail a clear place to belong.</p></li><li><span>03</span><h3>Manage with clarity</h3><p>Keep rent, maintenance and utilities connected as your everyday work takes shape.</p></li></ol>
        </Container>
      </section>

      <section className="hodi-home-cta" aria-labelledby="home-cta-title"><Container><div><SectionLabel>For the places you care for</SectionLabel><h2 id="home-cta-title">Make space for better<br />property management.</h2><p>Bring a little more clarity to every working day with HODI.</p></div><div className="hodi-home-cta-action"><Button href="/signup?type=landlord" variant="secondary" size="lg">Get Started</Button><span>Your next chapter starts here.</span></div></Container></section>
    </main>
  );
}
