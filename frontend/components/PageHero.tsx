type PageHeroProps = {
  title: string;
  description: string;
};

export default function PageHero({ title, description }: PageHeroProps) {
  return (
    <section className="hero">
      <h1>{title}</h1>
      <div className="hero-accent-line" />
      <p>{description}</p>
      <div className="header-overlay" aria-hidden="true" />
    </section>
  );
}
