"""Create a demonstration project without inventing scientific records."""
from app.db import Project, make_engine, make_session
def main():
    session_factory = make_session(make_engine())
    with session_factory() as session:
        name = "Tellurite Volumetric Display Research"
        if not session.query(Project).filter_by(name=name).first():
            session.add(Project(name=name, question="Investigate tellurite-based glasses for optical or volumetric-display applications. Identify compositions studied experimentally, dopants, synthesis routes, optical properties, thermal stability and major limitations. Compare the strongest candidates and identify what still requires experimental validation.", notes="Development example: no papers or scientific values have been pre-populated. Search the literature, inspect provenance, and save relevant papers."))
            session.commit()
    print("Sample project ready; no synthetic literature records added.")
if __name__ == "__main__":
    main()
