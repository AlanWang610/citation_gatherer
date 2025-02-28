// Function to find and open matching links
async function openMatchingLinks(tabId, settings) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: (patterns) => {
        const links = Array.from(document.querySelectorAll('a[href]'));
        const matchingLinks = links
          .map(link => link.href)
          .filter(href => {
            // Check if the href matches any of the patterns
            return patterns.some(pattern => {
              try {
                const regex = new RegExp(pattern);
                return regex.test(href) && !href.includes('supplementary-data');
              } catch (error) {
                console.error('Invalid regex pattern:', pattern, error);
                return false;
              }
            });
          });
        return [...new Set(matchingLinks)]; // Remove duplicates
      },
      args: [settings.openUrlPattern] // Changed from downloadUrlPattern to openUrlPattern
    });

    const uniqueLinks = result.result;
    console.log('Found matching links:', uniqueLinks);

    if (uniqueLinks.length > 0) {
      // Show notification about number of links found
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon48.png',
        title: 'Opening Links',
        message: `Found ${uniqueLinks.length} matching links. Opening them now...`
      });

      // Open each link in a new tab with a longer delay
      for (const url of uniqueLinks) {
        await chrome.tabs.create({ url, active: false });
        // Wait 1 second between opening tabs
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
  } catch (error) {
    console.error('Error opening links:', error);
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'Error Opening Links',
      message: 'An error occurred while opening links. Please try again.'
    });
  }
}

// Function to test if URL matches any pattern in the array
function matchesAnyPattern(url, patterns) {
  return patterns.some(pattern => {
    try {
      const regex = new RegExp(pattern);
      return regex.test(url);
    } catch (error) {
      console.error('Invalid regex pattern:', pattern, error);
      return false;
    }
  });
}

// Update the tab listener
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete') {
    console.log('Tab updated:', tab.url);
    chrome.storage.sync.get(
      {
        downloadUrlPattern: ['.*\\.example\\.com/.*'],
        openUrlPattern: [''],
        saveFolder: 'saved_pages',
        filenamePattern: '{hostname}_{pathname}',
        delay: 3,
        disableReferenceExpansion: false
      },
      (settings) => {
        try {
          console.log('Current settings:', settings);
          
          // Check if we're on a page that matches any open pattern
          if (settings.openUrlPattern.length > 0 && settings.openUrlPattern[0] !== '') {
            if (matchesAnyPattern(tab.url, settings.openUrlPattern)) {
              console.log('URL matches open pattern, searching for links...');
              openMatchingLinks(tabId, settings);
            }
          }

          // Check if we're on a page that matches any download pattern
          if (matchesAnyPattern(tab.url, settings.downloadUrlPattern)) {
            console.log('URL matches download pattern, scheduling save...');
            setTimeout(() => {
              console.log('Initiating save for tab:', tabId);
              saveHTML(tabId, settings).catch(error => {
                console.error('Error in saveHTML:', error);
              });
            }, settings.delay * 1000);
          }
        } catch (error) {
          console.error('Error in tab update handler:', error);
        }
      }
    );
  }
}); 
