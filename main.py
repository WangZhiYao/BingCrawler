import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from requests import HTTPError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import *

BING_API_URL = 'https://cn.bing.com/hp/api/model'
BING_API_PARAMS = {'mkt': 'zh-CN'}
BING_API_HEADERS = {'accept-language': 'zh-CN,zh;'}

TZ_SHANGHAI = timezone(timedelta(hours=8), name='Asia/Shanghai')
TODAY = datetime.now(TZ_SHANGHAI)

DB_ENGINE = 'sqlite:///bing.sqlite3'

IMAGE_DIR = Path('images')


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y.%m.%d %H:%M:%S'
    )


def initialize_database():
    engine = create_engine(DB_ENGINE)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    return session


def get_image():
    try:
        response = requests.get(BING_API_URL, params=BING_API_PARAMS, headers=BING_API_HEADERS)
        response.raise_for_status()
        api_model = ApiModel.from_dict(response.json())
        for media_content in api_model.media_contents:
            if datetime.strptime(media_content.full_date_string, '%Y %m月 %d').date() == TODAY.date():
                return media_content.image_content
    except HTTPError as e:
        logging.exception('get daily wallpaper failed.')
        raise e


def download_image(image_content):
    image = image_content.image
    image_url = get_image_url(image)
    image_file_name = get_image_file_name(image_url)
    logging.info("url: %s, filename: %s", image_url, image_file_name)
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        image_path = IMAGE_DIR / image_file_name
        with open(image_path, 'wb') as w:
            w.write(response.content)
    except Exception as e:
        logging.exception('image download failed')
        raise e


def get_image_url(image):
    image_url = image.url.replace('1920x1080', 'UHD').replace('webp', 'jpg')
    if not image_url.startswith('https://'):
        image_url = 'https://s.cn.bing.net/' + image_url
    return image_url


def get_image_file_name(image_url):
    return image_url.split('&')[0].split('=')[1].replace('OHR.', '')


def insert_to_db(session, image_content):
    image = image_content.image
    image_url = get_image_url(image)
    image_file_name = get_image_file_name(image_url)
    date = datetime.strptime(image_content.trivia_id.split('_')[1], '%Y%m%d')
    conv = lambda s: s or None
    bing_image = BingImage(
        year=date.year,
        month=date.month,
        day=date.day,
        headline=conv(image_content.headline),
        title=conv(image_content.title),
        copyright=conv(image_content.copyright),
        description=conv(image_content.description),
        location=conv(None),
        image=image_file_name
    )
    try:
        session.add(bing_image)
        session.commit()
    except Exception as e:
        logging.exception('insert to database failed', e)
        raise e


if __name__ == '__main__':
    setup_logging()
    session = initialize_database()
    image_content = get_image()
    download_image(image_content)
    insert_to_db(session, image_content)
