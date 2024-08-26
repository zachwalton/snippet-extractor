from quart import Quart, request, jsonify, render_template_string, redirect, url_for
from bs4 import BeautifulSoup
from requests_html import AsyncHTMLSession
from urllib.parse import urlparse, quote
import asyncio
import markdown2
import os

app = Quart(__name__)

README = """
# [snip.info](/)

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

#### Live Example

[Here!](/?url=https%3A%2F%2Ftruebpm.dance%2F%23readSpeed%3D573%26song%3D1%252C2%252C3%252C4%252C%2520007%2520-%2520NI-NI&selector=script&selector=style&selector=canvas&js=document.querySelector(%27.footer%27).remove()%3B&js=document.querySelector(%27.Content%27).remove()%3B&js=document.querySelector(%27.App-header%27).remove()%3B)

#### Playground

Enter the URL and add selectors or JS functions:

<form id="playground-form">
  <label for="url">URL:</label><br>
  <input type="text" id="url" name="url" style="width:100%; padding:8px;" placeholder="Enter the URL"><br><br>

  <div id="selectors-container">
    <div>
      <label for="selector1">Selector:</label><br>
      <input type="text" id="selector1" name="selector" style="width:85%; padding:8px;" placeholder="Enter a CSS selector">
      <button type="button" onclick="addField('selector', this)">+</button><br><br>
    </div>
  </div>

  <div id="js-container">
    <div>
      <label for="js1">Js:</label><br>
      <input type="text" id="js1" name="js" style="width:85%; padding:8px;" placeholder="Enter JavaScript code (optional)">
      <button type="button" onclick="addField('js', this)">+</button><br><br>
    </div>
  </div>

  <button type="button" onclick="submitForm()">Submit</button>
</form>

<div id="copy-link-container" style="margin-top:20px; display:none;">
  <a href="#" id="copy-link">Copy link...</a>
</div>

<iframe id="playground-result" style="width:100%; height:500px; margin-top:20px; display:none;"></iframe>
<div id="loading-spinner" style="display:none; text-align:center; margin-top:20px;">
  <p>Loading...</p>
</div>

<script>
  let selectorCount = 1;
  let jsCount = 1;

  function addField(type, button, value = '') {{
    const container = type === 'selector' ? document.getElementById('selectors-container') : document.getElementById('js-container');
    const count = type === 'selector' ? ++selectorCount : ++jsCount;
    
    const inputDiv = document.createElement('div');
    inputDiv.innerHTML = `<label for="${{type}}${{count}}">${{type.charAt(0).toUpperCase() + type.slice(1)}}:</label><br>
                          <input type="text" id="${{type}}${{count}}" name="${{type}}" style="width:85%; padding:8px;" placeholder="Enter ${{type === 'selector' ? 'a CSS selector' : 'JavaScript code (optional)'}}" value="${{value}}">
                          <button type="button" onclick="removeField(this)">-</button>
                          <button type="button" onclick="addField('${{type}}', this)">+</button><br><br>`;
    container.insertBefore(inputDiv, button.parentElement.nextSibling);

    // Ensure only the last field has a "+" button
    updateAddButtons(container);
  }}

  function removeField(button) {{
    const parentDiv = button.parentElement;
    const container = parentDiv.parentElement;
    parentDiv.remove();

    // Ensure only the last field has a "+" button
    updateAddButtons(container);
  }}

  function updateAddButtons(container) {{
    const divs = container.querySelectorAll('div');

    divs.forEach((div, index) => {{
      const plusButton = div.querySelector('button[onclick^="addField"]');

      if (index === divs.length - 1) {{
        if (!plusButton) {{
          const addButton = document.createElement('button');
          addButton.type = 'button';
          addButton.textContent = '+';
          addButton.setAttribute('onclick', `addField('${{container.id === 'selectors-container' ? 'selector' : 'js'}}', this)`);
          div.appendChild(addButton);
        }}
      }} else {{
        if (plusButton) plusButton.remove();
      }}
    }});
  }}

  function submitForm() {{
    document.getElementById('loading-spinner').style.display = 'block';
    document.getElementById('playground-result').style.display = 'none';
    
    const formData = new FormData(document.getElementById('playground-form'));
    const url = formData.get('url');
    const selectors = formData.getAll('selector').filter(Boolean).map(s => `selector=${{encodeURIComponent(s)}}`).join('&');
    const js = formData.getAll('js').filter(Boolean).map(j => `js=${{encodeURIComponent(j)}}`).join('&');
    const queryString = [selectors, js].filter(Boolean).join('&');
    const apiUrl = `/api/v1/snippet?url=${{encodeURIComponent(url)}}&${{queryString}}`;

    // Update query params in the address bar
    const newUrl = `${{window.location.pathname}}?url=${{encodeURIComponent(url)}}&${{queryString}}`;
    window.history.replaceState(null, '', newUrl);

    fetch(apiUrl)
      .then(response => response.text())
      .then(html => {{
        const iframe = document.getElementById('playground-result');
        const doc = iframe.contentWindow.document;
        doc.open();
        doc.write(html);
        doc.close();

        document.getElementById('loading-spinner').style.display = 'none';
        iframe.style.display = 'block';

        // Show and update the copy link
        const copyLinkContainer = document.getElementById('copy-link-container');
        const copyLink = document.getElementById('copy-link');
        copyLink.href = apiUrl;
        copyLink.textContent = "Copy link...";
        copyLinkContainer.style.display = 'block';
      }})
      .catch(error => {{
        console.error('Error:', error);
        document.getElementById('loading-spinner').style.display = 'none';
      }});
  }}

  function autoPopulateFields() {{
    const urlParams = new URLSearchParams(window.location.search);
    const url = urlParams.get('url');
    const selectors = urlParams.getAll('selector');
    const js = urlParams.getAll('js');

    if (url) {{
      document.getElementById('url').value = url;
    }}

    selectors.forEach((selector, index) => {{
      if (index === 0) {{
        document.getElementById('selector1').value = selector;
      }} else {{
        addField('selector', document.querySelector('#selectors-container div:last-child button[onclick^="addField"]'), selector);
      }}
    }});

    js.forEach((script, index) => {{
      if (index === 0) {{
        document.getElementById('js1').value = script;
      }} else {{
        addField('js', document.querySelector('#js-container div:last-child button[onclick^="addField"]'), script);
      }}
    }});

    // Ensure the buttons are correct after population
    updateAddButtons(document.getElementById('selectors-container'));
    updateAddButtons(document.getElementById('js-container'));

    if (url) {{
      submitForm();
    }}
  }}

  window.onload = autoPopulateFields;
</script>

[source](https://github.com/zachwalton/snippet-extractor)

"""

STYLES = """
<style>
    body {
        font-family: 'Helvetica Neue', Arial, sans-serif;
        margin: 0;
        padding: 0;
        background-color: #f4f4f4;
        color: #2c2c2c;
        line-height: 1.75;
        font-size: 16px;
    }

    .container {
        max-width: 900px;
        margin: 60px auto;
        padding: 40px;
        background-color: #ffffff;
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
        border-radius: 10px;
        border: 1px solid #e1e1e1;
    }

    h1, h2, h3 {
        color: #1c1c1c;
        text-align: center;
        margin: 1.5em 0 0.5em;
        font-weight: 700;
        letter-spacing: 0.05em;
    }

    h1 {
        border-bottom: 5px solid #1c1c1c;
        padding-bottom: 15px;
        margin-bottom: 1em;
        font-size: 2.75em;
        line-height: 1.2;
    }

    p, ul, ol {
        font-size: 1.125em;
        margin: 1em 0;
        color: #3c3c3c;
        line-height: 1.8;
    }

    code {
        background-color: #f2f2f2;
        padding: 8px 12px;
        border-radius: 4px;
        font-size: 1em;
        color: #d32f2f;
        font-family: 'Courier New', Courier, monospace;
    }

    pre {
        background-color: #2c2c2c;
        color: #f1f1f1;
        padding: 20px;
        border-radius: 10px;
        overflow-x: auto;
        font-size: 1em;
        line-height: 1.7;
    }

    a {
        color: #0056b3;
        text-decoration: none;
        font-weight: 600;
        transition: color 0.3s ease, text-decoration 0.3s ease;
    }

    a:hover {
        color: #003c82;
        text-decoration: underline;
    }

    ul, ol {
        padding-left: 40px;
    }

    ul li, ol li {
        margin-bottom: 12px;
    }
</style>
"""

INJECT="""
// First replace the hash with the hash from the upstream URL, if it exists
let url = new URL("{url}");
if (url.hash.length > 0) {{
    window.location.hash = url.hash;
}}

// Update the query params in the URL after page rendering
const newQueryParams = "{query_params}";
if (newQueryParams) {{
    const currentUrl = new URL(window.location);
    const params = new URLSearchParams(newQueryParams);

    // Merge the new params with the current ones
    for (const [key, value] of params.entries()) {{
        currentUrl.searchParams.set(key, value);
    }}

    // Update the browser's address bar without reloading the page
    window.history.replaceState(null, '', currentUrl.toString());
}}

// Save the original fetch function
const originalFetch = window.fetch;

window.fetch = async function (input, init) {{
    // Determine the URL (input can be a Request object or a URL string)
    let url = input instanceof Request ? input.url : input;

    // Check if the URL is relative (doesn't start with http:// or https://)
    if (!url.startsWith('http://') && !url.startsWith('https://')) {{
        // Get the current origin
        const origin = window.location.origin;

        // Construct the fully qualified URL
        const fullUrl = new URL(url, "{base_url}").href;

        // Encode the full URL
        const encodedUrl = encodeURIComponent(fullUrl);

        // Construct the final URL with corsproxy
        url = `https://corsproxy.io/?${{encodedUrl}}`;
    }}

    // If input was a Request object, clone it with the new URL
    if (input instanceof Request) {{
        input = new Request(url, input);
    }} else {{
        input = url;
    }}

    // Call the original fetch function with the modified input
    return originalFetch(input, init);
}};
"""

async def get(url):
    # Create an AsyncHTMLSession within the same event loop
    session = AsyncHTMLSession()
    try:
        response = await session.get(url)
        await response.html.arender(timeout=60)
        return response
    except asyncio.TimeoutError:
        raise IOError("Timeout Error: The page took too long to load. Please try again later.")
    except ConnectionError:
        raise IOError("Connection Error: Unable to establish a connection. Please check your internet connection or the URL.")
    except Exception as e:
        raise IOError(f"An unexpected error occurred while fetching or rendering the page: {e}")
    finally:
        await session.close()

@app.before_request
def before_request():
    if request.headers.get("X-Forwarded-Proto", "") == "http":
        url = request.url.replace('http://', 'https://', 1)
        code = 301
        return redirect(url, code=code)

@app.route('/')
async def index():
    html_content = markdown2.markdown(README.format(
        base_url=f"{request.scheme}://{request.host}".strip("/"),
    ))
    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <link rel="icon" href="{ url_for('static', filename='favicon.ico') }">
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>snip.info</title>
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
    query_params = request.query_string.decode()  # Get the full query string for injection

    if not url or not selectors:
        return jsonify({"error": "URL and at least one selector are required"}), 400

    parsed_url = urlparse(url)
    base_url = f'{parsed_url.scheme}://{parsed_url.netloc}'

    # Fetch the URL content
    try:
        response = await get(parsed_url.geturl())
    except IOError as e:
        return jsonify({"error": str(e)}), 503

    # Parse the HTML content
    try:
        soup = BeautifulSoup(response.html.raw_html, 'html.parser')
    except Exception as e:
        return jsonify({"error": f"Failed to parse HTML content: {str(e)}"}), 500

    # Replace relative links with absolute links via corsproxy.io
    for tag in soup.find_all(['a', 'img', 'link', 'script'], href=True):
        if tag['href'].startswith('http://') or tag['href'].startswith('https://'):
            continue
        encoded_url = quote(base_url + tag['href'])
        tag['href'] = f"https://corsproxy.io/?{encoded_url}"

    for tag in soup.find_all(['img', 'script'], src=True):
        encoded_url = quote(base_url + tag['src'])
        if tag['src'].startswith('http://') or tag['src'].startswith('https://'):
            continue
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

    # Patch fetch and update query params
    script_tag = soup.new_tag('script')
    script_tag.string = INJECT.format(url=parsed_url.geturl(), base_url=base_url, query_params=query_params)
    if soup.head is None:
        return jsonify({"error": f"No head tag found in result. Make sure to specify 'head' as a selector, or a child element of <head>"}), 400

    soup.head.append(script_tag)

    # Return the extracted elements as valid HTML
    return soup.prettify(), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.getenv("PORT", 5001))
