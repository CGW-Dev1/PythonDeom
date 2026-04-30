from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .database import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Listing(db.Model):
    __tablename__ = "rent_listings"
    __table_args__ = (
        db.UniqueConstraint("raw_hash", name="uq_listing_raw_hash"),
        db.Index("ix_listing_filter", "district", "house_type", "rent_price"),
    )

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(50), default="unknown", nullable=False)
    source_id = db.Column(db.String(120))
    detail_url = db.Column(db.String(500))
    district = db.Column(db.String(80), nullable=False, index=True)
    community = db.Column(db.String(160), nullable=False, index=True)
    rent_price = db.Column(db.Float, nullable=False, index=True)
    area = db.Column(db.Float, nullable=False)
    house_type = db.Column(db.String(80), nullable=False, index=True)
    orientation = db.Column(db.String(80))
    floor = db.Column(db.String(80))
    tags = db.Column(db.String(500))
    publish_time = db.Column(db.String(80))
    unit_price = db.Column(db.Float)
    raw_hash = db.Column(db.String(64), nullable=False)
    crawled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "source_id": self.source_id,
            "detail_url": self.detail_url,
            "district": self.district,
            "community": self.community,
            "rent_price": round(self.rent_price, 2),
            "area": round(self.area, 2),
            "house_type": self.house_type,
            "orientation": self.orientation or "",
            "floor": self.floor or "",
            "tags": self.tags or "",
            "publish_time": self.publish_time or "",
            "unit_price": round(self.unit_price or 0, 2),
            "crawled_at": self.crawled_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
