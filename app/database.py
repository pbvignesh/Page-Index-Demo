"""Database models + session. Three tables: filings, the PageIndex nodes, and
the extracted datasets. Kept intentionally small."""
from datetime import datetime, timezone

from sqlalchemy import create_engine, ForeignKey, String, Integer, Text, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config

engine = create_engine(config.DATABASE_URL, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


class Filing(Base):
    __tablename__ = "filings"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16))
    cik: Mapped[str] = mapped_column(String(16))
    company: Mapped[str] = mapped_column(String(200))
    form: Mapped[str] = mapped_column(String(12))
    period: Mapped[str] = mapped_column(String(24), default="")
    accession: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    nodes: Mapped[list["Node"]] = relationship(back_populates="filing", cascade="all, delete-orphan")
    datasets: Mapped[list["Dataset"]] = relationship(back_populates="filing", cascade="all, delete-orphan")


class Node(Base):
    """One node of the document tree — an Item/section of the filing."""
    __tablename__ = "nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id", ondelete="CASCADE"))
    order_ix: Mapped[int] = mapped_column(Integer, default=0)
    item: Mapped[str] = mapped_column(String(24))          # e.g. "Item 1A"
    title: Mapped[str] = mapped_column(String(200))        # e.g. "Risk Factors"
    summary: Mapped[str] = mapped_column(Text, default="")  # node summary, used for tree search
    text: Mapped[str] = mapped_column(Text, default="")     # section body
    intents: Mapped[list] = mapped_column(JSON, default=list)  # intent tags, set at ingest

    filing: Mapped["Filing"] = relationship(back_populates="nodes")


class Dataset(Base):
    """A structured table extracted from the filing (e.g. income statement)."""
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))     # e.g. "income_statement"
    label: Mapped[str] = mapped_column(String(120))   # human label + source citation
    columns: Mapped[list] = mapped_column(JSON, default=list)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    intents: Mapped[list] = mapped_column(JSON, default=list)  # intent tags, set at ingest

    filing: Mapped["Filing"] = relationship(back_populates="datasets")


def init_db():
    Base.metadata.create_all(engine)
