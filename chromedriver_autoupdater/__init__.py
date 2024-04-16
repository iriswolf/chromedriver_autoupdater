import io
import os
import zipfile
import logging
import tempfile
from enum import StrEnum
from pathlib import Path
from contextlib import suppress

import requests
from requests.exceptions import JSONDecodeError

__all__ = ['ChromeDriverUpdater', 'Channels', 'PlatformNames', 'UpdaterEndStatus']


class Texts:
    class Info:
        update_not_required = 'Обновление драйвера не требуется'
        successfully_installed = 'Драйвер успешно установлен! Версия - {0}'

    class Error:
        status_code_not_equals_200 = (
            'Сервер дал ответ отличный от 200. '
            'Возможно нет соединения с интернетом или сервер недоступен.'
        )

        fail_to_make_json = 'Не удалось преобразовать ответ сервера в json.'
        dest_path = 'Указанный путь является файлом или такой путь не существует.'
        invalid_platform = 'Неверное значение для `platform`. Нужно передать значение от `PlatformNames`'
        build_for_platform_not_found = 'Не найден билд для указанной платформы. Попробуйте указать другой канал.'
        channel_not_found = 'Не удалось получить версию с указанного канала. Возможно этот канал более не существует.'


class Channels(StrEnum):
    """ Каналы версий """
    Stable = 'Stable'
    Beta = 'Beta'
    Dev = 'Dev'
    Canary = 'Canary'


class PlatformNames(StrEnum):
    linux_x64 = 'linux64'
    mac_arm64 = 'mac-arm64'
    mac_x64 = 'mac-x64'
    win_x32 = 'win32'
    win_x64 = 'win64'


class UpdaterEndStatus(StrEnum):
    update_not_required = 'update_not_required'
    new_version_downloaded = 'new_version_downloaded'


class ChromeDriverUpdater:
    __versions_url = (
        'https://googlechromelabs.github.io'
        '/chrome-for-testing/last-known-good-versions-with-downloads.json'
    )
    __driver_filename = 'chromedriver'
    __current_version_filename = 'chromedriver_version'

    __dest_path: Path
    __logger: logging.Logger
    __selected_channel: Channels | str
    __selected_platform: PlatformNames | str
    __current_version_fp: Path

    def __init__(
            self,
            destination_path: str,
            platform: PlatformNames | str,
            version_channel: Channels | str = Channels.Stable
    ) -> None:
        self.__dest_path = Path(destination_path)
        self.__selected_channel = version_channel
        self.__selected_platform = platform

        self.__logger = logging.getLogger(__name__)
        self.__current_version_fp = self.__dest_path.joinpath(self.__current_version_filename)

        if not self.__dest_path.is_dir() or self.__dest_path.is_file():
            self.__logger.error(Texts.Error.dest_path)
            raise Exception(Texts.Error.dest_path)

    @staticmethod
    def __give_file_execute_permissions(fp: Path) -> None:
        os.chmod(fp, 0o755)

    @staticmethod
    def __remove_files_and_dir(path: Path) -> None:
        with suppress(Exception):
            for fp in path.iterdir():
                os.remove(fp)
            os.removedirs(path)

    def __make_request(self, url: str, method: str = 'GET', **kwargs) -> requests.Response:
        response = requests.request(
            method=method,
            url=url,
            **kwargs
        )

        self.__logger.debug(f'request status code - {response.status_code}')
        self.__logger.debug(f'request - {response.text}')

        if response.status_code != requests.codes.ok:
            self.__logger.error(Texts.Error.status_code_not_equals_200)
            raise Exception(Texts.Error.status_code_not_equals_200)

        return response

    def __make_request_json(self, url: str, **kwargs) -> dict:
        response = self.__make_request(url, **kwargs)

        try:
            response_json = response.json()
        except JSONDecodeError:
            self.__logger.error(Texts.Error.fail_to_make_json)
            raise Exception(Texts.Error.fail_to_make_json)

        return response_json

    def __get_versions_list(self) -> dict:
        return self.__make_request_json(self.__versions_url)

    def __get_version_from_channel(self) -> dict:
        versions_list = self.__get_versions_list()
        version = versions_list['channels'].get(self.__selected_channel)

        if version is None:
            self.__logger.error(Texts.Error.channel_not_found)
            raise Exception(Texts.Error.channel_not_found)

        return version

    def __get_current_version_number(self) -> str:
        return self.__get_version_from_channel()['version']

    def __write_version_to_file(self, version: str) -> None:
        with open(self.__current_version_fp, 'w', encoding='utf-8') as file:
            file.write(version)

    def __read_version_from_file(self) -> str:
        with open(self.__current_version_fp, 'r', encoding='utf-8') as file:
            return file.read()

    def __installed_version_is_outdated(self, current_server_version: str) -> bool:
        if not self.__current_version_fp.is_file():
            return True

        if self.__read_version_from_file() != current_server_version:
            return True

        return False

    def __get_driver_for_platform(self, version: dict) -> str:
        chromedriver_platforms: list[dict] = version['downloads']['chromedriver']

        for item in chromedriver_platforms:
            if item['platform'] != self.__selected_platform:
                continue
            return item['url']

        self.__logger.error(Texts.Error.build_for_platform_not_found)
        raise Exception(Texts.Error.build_for_platform_not_found)

    def __get_driver_filename_for_platform(self) -> str:
        driver_filename = self.__driver_filename
        driver_filename += '.exe' if self.__selected_platform.startswith('win') else ''
        return driver_filename

    def __remove_local_driver_file(self) -> None:
        with suppress(FileNotFoundError):
            os.remove(self.__dest_path.joinpath(self.__get_driver_filename_for_platform()))

    def __download_and_unzip_driver_file(self, url: str):
        """ Распаковывает файл драйвера из архива """
        response = self.__make_request(url)

        temp_path = Path(tempfile.mkdtemp())
        archive_folder_name = f'{self.__driver_filename}-{self.__selected_platform}'
        archive_folder_path = temp_path.joinpath(archive_folder_name)
        filename = self.__get_driver_filename_for_platform()

        archive_driver_fp = archive_folder_path.joinpath(filename)
        driver_dest_fp = self.__dest_path.joinpath(filename)

        # Распаковываем архив в Temp
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        archive.extractall(str(temp_path))

        # Перемещаем сам драйвер в указанную папку,
        # Удаляем папку из temp и даём драйверу права на выполнение
        os.rename(archive_driver_fp, driver_dest_fp)
        self.__remove_files_and_dir(temp_path)
        self.__give_file_execute_permissions(driver_dest_fp)

    def download_or_update(self) -> UpdaterEndStatus:
        version: dict = self.__get_version_from_channel()
        version_number: str = version['version']
        driver_url: str = self.__get_driver_for_platform(version)

        # Если локальная версия равна серверной
        if not self.__installed_version_is_outdated(version_number):
            self.__logger.info(Texts.Info.update_not_required.format(version_number))
            return UpdaterEndStatus.update_not_required

        self.__remove_local_driver_file()
        self.__download_and_unzip_driver_file(driver_url)
        self.__write_version_to_file(version_number)

        self.__logger.info(Texts.Info.successfully_installed.format(version_number))
        return UpdaterEndStatus.new_version_downloaded
