import json
from django.conf import settings
from django.utils import timezone
from cryptography.fernet import Fernet
from spotipy.cache_handler import CacheHandler
from spotipy import SpotifyOAuth, Spotify, SpotifyException, SpotifyOauthError
from . import models


scopes = ['user-read-currently-playing', 'user-read-playback-state', 'user-modify-playback-state']


class DjangoCacheHandler(CacheHandler):
    """ Custom Spotipy cache handler. Saves authentication information to the database. """

    def __init__(self, user, account_id=None):
        self.user = user
        self.account = account_id

    def get_cached_token(self):
        account = models.SpotifyUser.objects.filter(pk=self.account).first()
        if not self.user:
            raise SpotifySessionError("Account owner must be specified to retrieve token")

        if not account:
            account = models.SpotifyUser.objects.create(user=self.user)
            self.account = account.pk

        if self.user != account.user:
            raise SpotifySessionError("Invalid account ID for user %s" % self.user.name)

        if not account.token_info:
            return None

        try:
            cipher_suite = Fernet(settings.CRYPTO_KEY)
        except ValueError:
            raise SpotifySessionError("Cryptographic key is either missing or invalid")
        return json.loads(cipher_suite.decrypt(account.token_info.encode('utf-8')))

    def save_token_to_cache(self, token_info):
        account = models.SpotifyUser.objects.filter(pk=self.account).first()
        if not self.user:
            raise SpotifySessionError("Account owner must be specified to save token")

        if not account:
            account = models.SpotifyUser.objects.create(user=self.user)
            self.account = account.pk

        try:
            cipher_suite = Fernet(settings.CRYPTO_KEY)
        except ValueError:
            raise SpotifySessionError("Cryptographic key is either missing or invalid")
        encrypted_token_info = cipher_suite.encrypt(json.dumps(token_info).encode('utf-8')).decode('utf-8')

        account.token_info = encrypted_token_info
        account.save()


class SpotifySessionError(Exception):
    def __init__(self, message, error=None, error_description=None, *args, **kwargs):
        self.error = error
        self.error_description = error_description
        self.__dict__.update(kwargs)
        super(SpotifySessionError, self).__init__(message, *args, **kwargs)


def get_spotify_session(account, request_user):
    """
    Call this method to get a Spotify session for a specific Spotify account.

    :param account: SpotifyUser object
    :param request_user: The user currently logged in (User object)
    :return: A Spotify object (manages the session and API calls)
    """

    if account.personal and request_user != account.user:
        raise SpotifySessionError("User is not permitted to access this account")

    cache_handler = DjangoCacheHandler(account.user, account.pk)
    state = "u%da%d" % (account.user.pk, account.pk)

    try:
        auth_manager = SpotifyOAuth(client_id=settings.SPOTIFY_CLIENT_ID, client_secret=settings.SPOTIFY_CLIENT_SECRET,
                                    redirect_uri=settings.SPOTIFY_REDIRECT_URI, state=state, scope=' '.join(scopes),
                                    cache_handler=cache_handler)
    except SpotifyOauthError as error:
        raise SpotifyException(403, "SpotifyOAuth", str(error))

    return Spotify(auth_manager=auth_manager)


def get_track(session, identifier):
    """
    Retrieves the metadata for a given item in Spotify

    :param session: A Session object (used for authenticating the request)
    :param identifier: The unique Spotify ID for the item
    :return: Item metadata, if available (Dictionary)
    """

    try:
        api = get_spotify_session(session.user, session.user.user)
        return api.track(identifier)
    except SpotifyException:
        return None


def add_to_queue(song_request, request_user):
    """
    Attempt to add a track to the Spotify queue

    :param song_request: Song request object
    :param request_user: The user currently logged in (User object)
    :return: None on success; SpotifyException otherwise
    """

    try:
        api = get_spotify_session(song_request.session.user, request_user)
        api.add_to_queue(song_request.identifier)
        song_request.queued = timezone.now()
        song_request.save()
    except SpotifyException as error:
        return error
    return None


def queue_estimate(session, ms=False):
    """
    Attempt to determine wait time for new song requests

    :param session: The corresponding Session object
    :param ms: If True, return the estimate in milliseconds
    :return: Time remaining, if available (Int)
    """

    currently_playing = get_currently_playing(session)
    if not currently_playing:
        return None
    progress = currently_playing['progress_ms']
    item = currently_playing['item']['id']
    current_song = models.SongRequest.objects.filter(identifier=item, session=session).first()
    time_remaining = 0
    if current_song and current_song.queued:
        time_remaining += current_song.duration - progress
        upcoming = models.SongRequest.objects.filter(queued__gt=current_song.queued, session=session)
        for request in upcoming:
            time_remaining += request.duration
        if not ms:
            time_remaining = int(time_remaining / 60000)
        return time_remaining
    return None


def get_currently_playing(session):
    """
    Attempts to get details about what is currently playing in Spotify

    :param session: The corresponding Session object
    :return: Item metadata, if available (Dictionary)
    """

    try:
        api = get_spotify_session(session.user, session.user.user)
        return api.currently_playing()
    except SpotifyException:
        return None


def get_playback_state(session):
    """
    Retrieves information about the session's current playback state

    :param session: The corresponding Session object
    :return: Playback state information (Dictionary)
    """

    try:
        api = get_spotify_session(session.user, session.user.user)
        return api.current_playback()
    except SpotifyException:
        return None


def get_available_devices(account):
    """
    Retrieves information about a Spotify user's available devices

    :param account: The corresponding SpotifyUser object
    :return: Device info (List of Dictionaries)
    """

    try:
        api = get_spotify_session(account, account.user)
        return api.devices()
    except SpotifyException:
        return None


def play(session, device=None):
    """
    Starts or resumes playback for a given session.

    :param session: The corresponding Session object
    :param device: The unique id of the device to start playback on
    :return: None (if successful); Error message otherwise (string)
    """

    try:
        api = get_spotify_session(session.user, session.user.user)
        return api.start_playback(device)
    except SpotifyException as e:
        return e.msg.split('\n')[-1]


def pause(session):
    """
    Pause playback for a given session.

    :param session: The corresponding Session object
    :return: None (if successful); Error message otherwise (string)
    """

    try:
        api = get_spotify_session(session.user, session.user.user)
        return api.pause_playback()
    except SpotifyException as e:
        return e.msg.split('\n')[-1]


def previous(session):
    """
    Skip to the previous track.

    :param session: The corresponding Session object
    :return: None (if successful); Error message otherwise (string)
    """

    try:
        api = get_spotify_session(session.user, session.user.user)
        return api.previous_track()
    except SpotifyException as e:
        return e.msg.split('\n')[-1]


def skip(session):
    """
    Skip to the next track.

    :param session: The corresponding Session object
    :return: None (if successful); Error message otherwise (string)
    """

    try:
        api = get_spotify_session(session.user, session.user.user)
        return api.next_track()
    except SpotifyException as e:
        return e.msg.split('\n')[-1]
