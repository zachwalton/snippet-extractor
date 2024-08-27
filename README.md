# Snippet Extractor

This service allows you to extract specific elements from a web page based on CSS selectors and optionally inject custom JavaScript. In addition to selected elements, parent elements are included (but not siblings).

It loads the page with Chromium and returns the page after JS rendering, so is more likely to be correct than basic scrapers.

It also replaces relative links with links to the destination domain, proxied through [corsproxy.io](https://corsproxy.io) to work around CORS errors.

Finally, it patches `window.fetch` to send relative requests to the upstream domain, and has some other neat tricks like loading `window.location.hash` and `window.location.search` from the upstream URL for triggering behavior in PWAs.

## Endpoints

### GET /api/v1/snippet

- `url`: The URL of the web page to extract content from
- `selector` (repeating): CSS selector(s) to identify the elements you want to extract
  - Selector syntax is [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- `js` (optional, repeating): Custom JavaScript function(s) to run after all other scripts on the page

#### Example Request

`GET /api/v1/snippet?url=http://example.com&selector=.header&js=document.querySelector('.footer').remove();`

## Development

To develop this site, you need `snip.localdev` to resolve locally and support `*.snip.localdev` wildcard lookups for proxying to work.

On MacOS, install/configure dnsmasq as follows (adjust the path to your homebrew accordingly):

```bash
➜ brew install dnsmasq
➜ cat /opt/homebrew/etc/dnsmasq.conf
address=/.snip.localdev/127.0.0.1
address=/snip.localdev/127.0.0.1
➜ cat /etc/resolver/snip.localdev
nameserver 127.0.0.1
```

Then `sudo brew services restart dnsmasq`. You should then be able to run `pip install -r requirements.txt` and `python app.py` and browse to http://snip.localdev:5001.
