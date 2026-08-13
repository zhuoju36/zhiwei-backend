"""SQLAlchemy 异步引擎与会话工厂。"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=20,  # 高频场景需要大连接池
    max_overflow=30,
    pool_pre_ping=True,  # 自动检测断连
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
