from quart import Quart, request, jsonify, render_template_string
from bs4 import BeautifulSoup
from requests_html import AsyncHTMLSession
from urllib.parse import urlparse, quote
import asyncio
import markdown2
import os

app = Quart(__name__)

README = """
# Snippet Extractor

This service allows you to extract specific elements from a web page based on CSS selectors and optionally inject custom JavaScript. In addition to selected elements, parent elements are included (but not siblings).

It loads the page with Chromium and returns the page after JS rendering, so is more likely to be correct than basic scrapers.

It also replaces relative links with links to the destination domain, proxied through [corsproxy.io](https://corsproxy.io) to work around CORS errors.

Finally, it patches `window.fetch` to send relative requests to the upstream domain.

## Endpoints

### GET /api/v1/snippet

- `url`: The URL of the web page to extract content from
- `selector` (repeating): CSS selector(s) to identify the elements you want to extract
  - Selector syntax is [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- `js` (optional, repeating): Custom JavaScript function(s) to run after all other scripts on the page

#### Example Request
`GET /api/v1/snippet?url=http://example.com&selector=.header&js=document.querySelector('.footer').remove();`

#### Live Example

Extract just the chart from [truebpm.dance](https://truebpm.dance), with custom JS to remove elements rendered by JS after page load: [here]({base_url}/api/v1/snippet?url=https%3A%2F%2Ftruebpm.dance%2F%23readSpeed%3D573%26song%3D1%252C2%252C3%252C4%252C%2520007%2520-%2520NI-NI&selector=script&selector=style&selector=canvas&script:(src=*)&js=document.querySelector(%27.footer%27).remove();&js=document.querySelector(%27.Content%27).remove();&js=document.querySelector(%27.App-header%27).remove();)

[source](https://github.com/zachwalton/snippet-extractor)

"""

STYLES = """
<style>
    body {
        font-family: Arial, sans-serif;
        margin: 0;
        padding: 0;
        background-color: #f4f4f4;
        color: #333;
        line-height: 1.6;
    }
    .container {
        width: 80%;
        margin: auto;
        overflow: hidden;
    }
    h1, h2, h3 {
        color: #333;
        text-align: center;
        margin-top: 1.5em;
    }
    h1 {
        border-bottom: 2px solid #333;
        padding-bottom: 10px;
    }
    p, ul, ol {
        font-size: 1.1em;
        margin: 20px 0;
    }
    code {
        background-color: #eaeaea;
        padding: 2px 5px;
        border-radius: 3px;
        font-size: 1.1em;
    }
    pre {
        background-color: #333;
        color: #f4f4f4;
        padding: 10px;
        border-radius: 5px;
        overflow-x: auto;
    }
    a {
        color: #1a73e8;
        text-decoration: none;
    }
    a:hover {
        text-decoration: underline;
    }
</style>
"""

FETCH="""
// Save the original fetch function
const originalFetch = window.fetch;

window.fetch = async function (input, init) {
    // Determine the URL (input can be a Request object or a URL string)
    let url = input instanceof Request ? input.url : input;

    // Check if the URL is relative (doesn't start with http:// or https://)
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        // Get the current origin
        const origin = window.location.origin;

        // Construct the fully qualified URL
        url = new URL(url, {base_url}).href;
    }

    // If input was a Request object, clone it with the new URL
    if (input instanceof Request) {
        input = new Request(url, input);
    } else {
        input = url;
    }

    // Call the original fetch function with the modified input
    return originalFetch(input, init);
};

"""

async def get(url):
    # Create an AsyncHTMLSession within the same event loop
    session = AsyncHTMLSession()
    try:
        response = await session.get(url)
        await response.html.arender()
        return response
    except Exception as e:
        raise IOError(f"Failed to fetch or render the page: {e}")
    finally:
        await session.close()

@app.route('/')
async def index():
    html_content = markdown2.markdown(README.format(
        base_url=f"{request.scheme}://{request.host}".strip("/"),
    ))
    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Snippet Extraction API</title>
        {STYLES}
    </head>
    <body>
        <div class="container">
            {html_content}
        </div>
    </body>
    </html>
    """
    return await render_template_string(full_html)


@app.route('/api/v1/snippet', methods=['GET'])
async def extract():
    url = request.args.get('url')
    selectors = request.args.getlist('selector')
    js_code = request.args.getlist('js')  # Get the JavaScript code from query parameter

    if not url or not selectors:
        return jsonify({"error": "URL and at least one selector are required"}), 400

    parsed_url = urlparse(url)
    base_url = f'{parsed_url.scheme}://{parsed_url.netloc}'

    # Fetch the URL content
    try:
        response = await get(base_url)
    except IOError as e:
        return jsonify({"error": str(e)}), 503

    # Parse the HTML content
    try:
        soup = BeautifulSoup(response.html.raw_html, 'html.parser')
    except Exception as e:
        return jsonify({"error": f"Failed to parse HTML content: {str(e)}"}), 500

    # Replace relative links with absolute links via corsproxy.io
    for tag in soup.find_all(['a', 'img', 'link', 'script'], href=True):
        encoded_url = quote(base_url + tag['href'])
        tag['href'] = f"https://corsproxy.io/?{encoded_url}"

    for tag in soup.find_all(['img', 'script'], src=True):
        encoded_url = quote(base_url + tag['src'])
        tag['src'] = f"https://corsproxy.io/?{encoded_url}"

    # Find elements matching the selectors
    matched_elements = []
    for selector in selectors:
        try:
            elements = soup.select(selector)
            if not elements:
                return jsonify({"error": f"No elements found for selector: {selector}"}), 400
            matched_elements.extend(elements)
        except Exception as e:
            return jsonify({"error": f"Invalid selector: {selector}"}), 400

    # Create a set to keep track of elements to preserve (and their parents)
    elements_to_keep = set()

    for element in matched_elements:
        elements_to_keep.add(id(element))
        parent = element
        while parent is not None and parent != soup:
            elements_to_keep.add(id(parent))
            parent = parent.parent

    # Remove all elements not in the elements_to_keep set
    for element in soup.find_all(True):
        if id(element) not in elements_to_keep:
            element.decompose()

    # If js query parameter is provided, add it as a script at the end of the body
    if js_code:
        for js in js_code:
            script_tag = soup.new_tag('script')
            script_tag.string = js
            soup.body.append(script_tag)  # Ensure the script is appended after all other scripts

    # Patch fetch
    script_tag = soup.new_tag('script')
    script_tag.string = FETCH.format(base_url=base_url)
    soup.body.append(script_tag)

    # Return the extracted elements as valid HTML
    return soup.prettify(), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.getenv("PORT", 5001))
