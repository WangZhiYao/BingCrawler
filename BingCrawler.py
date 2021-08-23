import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import Column, String, Integer, create_engine, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y.%m.%d %H:%M:%S')

BING_URL = 'https://cn.bing.com/'
BING_IMAGE_URL = BING_URL + 'HPImageArchive.aspx'
BING_PARAMS = {'format': 'js', 'idx': '0', 'n': '1', 'mkt': 'zh-CN'}

TZ_SHANGHAI = timezone(timedelta(hours=8), name='Asia/Shanghai')
TODAY = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(TZ_SHANGHAI)

DB_ENGINE = 'sqlite:///bing.sqlite3'
Base = declarative_base()

IMAGE_DIR = Path('images')


class BingImage(Base):
    __tablename__ = 't_bing_image'

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer)
    month = Column(Integer)
    day = Column(Integer)
    copyright = Column(String)
    title = Column(String)
    description = Column(String)
    location = Column(String)
    image = Column(String)

    def __init__(self, year, month, day, copyright, title, description, location, image):
        self.year = year
        self.month = month
        self.day = day
        self.copyright = copyright
        self.title = title
        self.description = description
        self.location = location
        self.image = image


engine = create_engine(DB_ENGINE)
Base.metadata.create_all(engine, Base.metadata.tables.values(), checkfirst=True)
Session = sessionmaker(bind=engine)
session = Session()


class CrawlerException(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


@retry(retry=retry_if_exception_type(CrawlerException), stop=stop_after_attempt(3), wait=wait_fixed(5), )
def get_hp_image_archive():
    response = requests.get(BING_IMAGE_URL, params=BING_PARAMS)
    response.raise_for_status()
    hp_image_archive = json.loads(response.text)
    is_image_updated(hp_image_archive)
    download_image(hp_image_archive)
    insert_to_db(hp_image_archive)


def is_image_updated(hp_image_archive):
    if hp_image_archive['images']:
        image = hp_image_archive['images'][0]
        image_date = image['enddate']
        if image_date != TODAY.strftime('%Y%m%d'):
            raise CrawlerException('date not updated.')


def download_image(hp_image_archive):
    try:
        image = hp_image_archive['images'][0]
        image_url = image['url'][1:]
        image_file_name = image_url.split('&')[0].replace('th?id=OHR.', '')
        response = requests.get(BING_URL + image_url, stream=True)
        response.raise_for_status()

        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        image_path = IMAGE_DIR / image_file_name
        with open(image_path, 'wb') as w:
            w.write(response.content)
    except Exception as e:
        logging.exception(e)
        raise CrawlerException('download image failed')


def insert_to_db(hp_image_archive):
    try:
        image = hp_image_archive['images'][0]
        image_url = image['url'][1:]
        image_file_name = image_url.split('&')[0].replace('th?id=OHR.', '')
        date = datetime.strptime(image['enddate'], '%Y%m%d')
        conv = lambda s: s or None
        bing_image = BingImage(
            date.year,
            date.month,
            date.day,
            conv(image.get('copyright', None)),
            conv(image.get('title', None)),
            conv(image.get('description', None)),
            conv(image.get('location', None)),
            image_file_name
        )
        session.add(bing_image)
        session.commit()
    except Exception as e:
        logging.exception(e)
        raise CrawlerException('insert to database failed.')


if __name__ == '__main__':
    get_hp_image_archive()
