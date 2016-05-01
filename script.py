import csv
import nltk
import twitter
import collections
from argparse import ArgumentParser
from twitter import Twitter, auth, OAuth
from nltk.corpus import stopwords
from sentiment import StanfordNLP, VALUES
import config

slangs = {}
with open('slangs_meaning.csv', 'r') as sf:
    reader = csv.DictReader(sf)
    for row in reader:
        slangs[row['slang']] = row['meaning']


def data_pre_processing(tweet):
    '''Data pre-processing is done in this method
    step 1: Replace the slangs with their actual meaning
    ex: gr8 - great
    step 2: Replace  the emoticons with sentiment
    ex: :) - positive, :( - negative
    step 3: Remove the stop words
    ex: this -
    step 4: Replace user tags with ||U||
    ex: @vivekanand1101 - ||U||
    step 5: Replace the links with ||L||
    ex: http://facebook.com = ||L||
    step 6: Replace all the negations with "NOT"
    ex: not, no, never, n't, cannot - NOT
    '''

    if tweet == ' ':
        return None

    #replace the slangs
    tokens = tweet.split(' ')
    for i in range(len(tokens)):
        for key in slangs.keys():
            if key == tokens[i]:
                tokens[i] = slangs[key]


    #replace the emoticons
    for i in range(len(tokens)):
        for key in config.EMOTICONS.keys():
            if key == tokens[i]:
                tokens[i] = config.EMOTICONS[key]


    #replace the links
    #replace the users
    #replace the negations
    for token in range(len(tokens)):
        if tokens[token].startswith('http') or tokens[token].startswith('www'):
            tokens[token] = '||L||'

        elif tokens[token].startswith('@'):
            tokens[token] = '||T||'

        elif tokens[token] in ['not', 'no', 'never', 'n\'t', 'cannot']:
            tokens[token] = 'NOT'


    #remove the stopwords (english only)
    stop = stopwords.words("english")
    tokens_ = []
    for i in tokens:
        if i not in stop:
            tokens_.append(i)

    tokens = tokens_


    tokens = [' ' + token + ' ' for token in tokens]
    tweet = "".join(tokens)
    return tweet


def categorize_sentiment(result):
    """Calculates the sum of the sentiments.
        Each type of sentiment is assigned some value
        in the VALUES dictionary
    """
    if result[0]['sentiment'] == "Negative":
        return 'Negative'
    elif result[0]['sentiment'] == "Very Negative":
        return 'Very Negative'
    elif result[0]['sentiment'] == "Positive":
        return 'Positive'
    elif result[0]['sentiment'] == "Very Positive":
        return 'Very Positive'
    else:
        return 'Neutral'


def process(tweets, details):
    ''' Get the overall sentiment of the tweets '''

    overall = 0
    for tweet in tweets:

        usable_tweet = data_pre_processing(tweet['text'].encode('utf-8'))

        if not usable_tweet:
            continue

        nlp = StanfordNLP()
        results = nlp.parse(usable_tweet)
        result = results['sentences']
        sentiment = categorize_sentiment(result)
        value = VALUES[sentiment]
        overall += value

        if details:
            print 'Original tweet: ', tweet['text'].encode('utf-8')
            print 'Post Pre Processed tweet: ', usable_tweet
            print 'The sentiment of tweet as processed by corenlp: ', sentiment
            print '--------------------------------------------------'

    print 'The overall sentiment of the recieved tweets is: '
    if overall > 0:
        print 'Positive'
    else:
        print 'Negative'


class Tweets():
    ''' To get tweets via search or user tweets '''

    def __init__(self):
        self.t = Twitter(auth=OAuth( \
                    config.TOKEN,
                    config.TOKEN_KEY,
                    config.CON_SECRET,
                    config.CON_SECRET_KEY)
        )

    def search(self, query):
        ''' Get the tweets via searching through twitter '''
        tweets = self.t.search.tweets(q=query)
        return tweets


    def user(self, user):
        ''' Get the tweets of a particular user '''
        tweets = self.t.statuses.user_timeline(screen_name=user)
        return tweets


def main():
    parser = ArgumentParser(description='Sentiment Analysis of twitter reviews')
    parser.add_argument('-s', '--search', help='If you want to extract tweets \
            by searching through twitter')
    parser.add_argument('-u', '--user', help='If you want the tweets of a \
            particular user')
    parser.add_argument('-d', '--details', default=False, help='If you want to \
            see the details of each step for each tweet')

    args = parser.parse_args()
    if not any([args.search or args.user]):
        print 'Either search or get tweets of a user'
        print 'Use either: --user vivekanand1101 or --search \'#Amazon\''
        return

    if args.search and args.user:
        print 'You can not use both --user and --search at the same time -_- '
        return

    if args.search:
        tweet = Tweets()
        tweets = tweet.search(args.search)['statuses']

    if args.user:
        tweet = Tweets()
        tweets = tweet.user(args.user)

    if not tweets:
        print 'Couldn\'t fetch any tweets, try again'
        return
    process(tweets, args.details)


if __name__ == '__main__':
    main()
