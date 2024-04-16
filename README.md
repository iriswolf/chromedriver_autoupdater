# chromedriver_autoupdater
Проверяет есть ли обновление chromedriver и обноляет, либо если его нет совсем, то скачивает

Обновлений не будет, документации тоже. Читайте код.
<br>
Сделал чисто для себя, если нужны какие-то изменения - делайте форк


## Установка
poetry:
<br>
```poetry add git+https://github.com/iriswolf/chromedriver_autoupdater```

pip:
<br>
```pip install git+https://github.com/iriswolf/chromedriver_autoupdater```

## Использование
```python
import logging
from chromedriver_autoupdater import ChromeDriverUpdater, PlatformNames

logging.basicConfig(level=logging.INFO)


if __name__ == '__main__':
    cdu = ChromeDriverUpdater('.', PlatformNames.win_x64)
    cdu.download_or_update()
```