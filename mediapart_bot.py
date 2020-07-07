import os
import tempfile
import logging
import schedule
import time
import shutil
from slack import WebClient
from slack.errors import SlackApiError
from mediapart_parser import MediapartParser
from tinydb import TinyDB
from tinydb import Query

# Resolve directories
articles_tmp_folder = tempfile.gettempdir() + "/mediapart_bot/articles"
logs_file = tempfile.gettempdir() + "/mediapart_bot/logs.app"

# Environment variables
bot_fetch_time_hours = int(os.environ['BOT_FETCH_TIME_HOURS'])
mediapart_channel_id = os.environ['CHANNEL_ID']
slack_token = os.environ['SLACK_BOT_TOKEN']


def sendMessage(file_name, file_path, article_title):
    try:
        response = client.files_upload(
            channels=mediapart_channel_id,
            file=file_path,
            filename=file_name,
            filetype="pdf",
            title=article_title
        )
        assert response["file"]

    except SlackApiError as e:
        clean_temp_folder()
        logging.error(str(e), exc_info=True)


def get_last_articles():

    try:
        parser = get_mediapart_parser()
        all_article_links = parser.get_last_french_articles_links()

        # if no new articles, exit method
        new_articles_number = resolve_new_articles_numbers(all_article_links)
        if new_articles_number == 0:
            logging.debug("No new articles to fetch.")
            return

        logging.debug("Fetching %s new articles", str(new_articles_number))

        all_article_titles = parser.get_last_articles_titles()
        all_articles_categories = parser.get_last_articles_categories()

        User = Query()

        for article_number in range(len(all_article_titles)):

            # resolve article id
            article_link = all_article_links[article_number]
            article_id = parser.get_article_id(article_link)

            # check if article id is found in the database
            result = mediapart_database.search(User.articleId == article_id)

            # if the article id is not already in the database
            if not result:
                article_title = all_article_titles[article_number]
                article_category = all_articles_categories[article_number]
                article_file_name = resolve_article_file_name(article_id)
                final_file_path = articles_tmp_folder + "/" \
                    + article_file_name + ".pdf"

                parser.download_article(article_id, final_file_path)

                content = "[" + article_category + "] " + article_title
                sendMessage(article_file_name + ".pdf",
                            final_file_path, content)

                mediapart_database.insert({"articleId": article_id})

        clean_temp_folder()

    except Exception as e:
        clean_temp_folder()
        logging.error(str(e), exc_info=True)


def resolve_new_articles_numbers(all_article_links):
    User = Query()
    parser = get_mediapart_parser()

    new_articles_number = 0

    for article_link in all_article_links:
        article_id = parser.get_article_id(article_link)

        result = mediapart_database.search(User.articleId == article_id)

        if not result:
            new_articles_number = new_articles_number + 1
    return new_articles_number


def resolve_article_file_name(article_id):
    base_name = "article"
    file_name = base_name + "_" + article_id
    return file_name


def get_mediapart_parser():
    mediapart_user = os.environ['MEDIAPART_USER']
    mediapart_password = os.environ['MEDIAPART_PWD']

    return MediapartParser(mediapart_user, mediapart_password)


def create_folder(folder_path):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)


def clean_temp_folder():
    for filename in os.listdir(articles_tmp_folder):
        file_path = os.path.join(articles_tmp_folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print("Failed to delete %s. Reason: %s" % (file_path, e))


# clean and prepare folders
create_folder(articles_tmp_folder)
clean_temp_folder()

# Configure database
mediapart_database = TinyDB(tempfile.gettempdir()
                            + "/mediapart_bot/mediapart_database.json")
# Configure logger
logging.basicConfig(
    filename=logs_file,
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Start the bot
client = WebClient(slack_token)
get_last_articles()
schedule.every(bot_fetch_time_hours).hours.do(get_last_articles)

while True:
    schedule.run_pending()
    time.sleep(1)
