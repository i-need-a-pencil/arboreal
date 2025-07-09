const colorMappingSVG = {
    "Sufficiency":     "rgb(13,110,253)",   // 0d6efd
    "Verbosity":       "rgb(13,253,49)",    // 0dfd31
    "Hallucinations":  "rgb(253,13,97)",    // fd0d61
    "Completeness":    "rgb(215,205,17)",   // d7cd11
    "Unlabel":         "rgb(147, 112, 219)"
};

const colorMappingHTML = {
    "Sufficiency":    "#0d6efd",
    "Completeness":   "#d7cd11",
    "Hallucinations": "#fd0d61",
    "Verbosity":      "#0dfd31",
    "Unlabel":        "lightgray"
};

const STROKE = '5';
const STROKE_BASE = '1';


function applySavedAnnotations() {

    // yeah, horrible
    for (let metric of ["Sufficiency","Completeness","Hallucinations","Verbosity"]) {

     (nodesMap[metric]||[]).forEach(name => {
       const a = document.querySelector(`a[*|href="javascript:markNode('${name}')"]`);
       if (!a) {
         console.log("Could not find " + name);
         return;
       }
       const rect = a.querySelector('rect');
       rect.style.stroke = colorMappingSVG[metric];
       rect.style.strokeWidth = STROKE;
     });
   }

   tagify.addTags(missing);
   document.querySelector("#notes-input").value = notes;
}

function extractAllNodes() {
  const aList = document.querySelectorAll("a[*|href*='javascript:markNode']");
  var allNodes = [];

  for (let node of aList) {
    nodeName = node.href.baseVal.replace(/javascript:markNode\(\'(.*)\'\)/mg, '$1');
    allNodes.push(nodeName);
  }
  return new Set(allNodes);
}

function updateLocalProgress() {
  const allNodes = extractAllNodes();
  const labeledNodes = new Set([...nodesMap["Sufficiency"],
                                ...nodesMap["Completeness"],
                                ...nodesMap["Hallucinations"],
                                ...nodesMap["Verbosity"]]);

  const unlabeledNodes = Array.from(allNodes.difference(labeledNodes));
  document.querySelector("#sufficiency-list").innerHTML = nodesMap["Sufficiency"].join(' ');
  document.querySelector("#completeness-list").innerHTML = nodesMap["Completeness"].join(' ');
  document.querySelector("#hallucinations-list").innerHTML = nodesMap["Hallucinations"].join(' ');
  document.querySelector("#verbosity-list").innerHTML = nodesMap["Verbosity"].join(' ');
  document.querySelector("#unlabeled-list").innerHTML = '[' + JSON.stringify(unlabeledNodes.length) + '] ' + unlabeledNodes.join(' ');
}

function markNode(nodeName) {

    const metric = document.querySelector('input[name="option"]:checked').id;
    const a = document.querySelector(`a[*|href="javascript:markNode('${nodeName}')"]`);

    if (!a) {
        alert('${nodeName} not found');
        return;
    }

    const rect = a.querySelector('rect');

    if (metric !== "Unlabel") {
      if (nodesMap[metric].length > 0 && nodesMap[metric][0] == nodeName) {
        // remove from all
        rect.style.stroke = '';
        rect.style.strokeWidth = STROKE_BASE;
        for (let m of ["Sufficiency","Completeness","Hallucinations","Verbosity"]) {
            nodesMap[m] = (nodesMap[m]||[]).filter(n => n !== nodeName);
        }
        console.log("UNLABELing (same color) nodesMap[metric]: " + nodesMap[metric] + " for " + metric);
      } else {
        // getting corresponding color
        rect.style.stroke = colorMappingSVG[metric];
        // setting width
        rect.style.strokeWidth = STROKE;
        // removing previous annotations of this node
        for (let m of ["Sufficiency","Completeness","Hallucinations","Verbosity"]) {
          nodesMap[m] = (nodesMap[m]||[]).filter(n => n !== nodeName);
        }
        // adding as unique element of the array
        nodesMap[metric] = Array.from(new Set([...(nodesMap[metric]||[]), nodeName]));
        console.log("nodesMap[metric]: `" + nodesMap[metric] + "` for " + metric);
      }
    } else {
      // remove from all
      rect.style.stroke = '';
      rect.style.strokeWidth = STROKE_BASE;

      for (let m of ["Sufficiency","Completeness","Hallucinations","Verbosity"]) {
        nodesMap[m] = (nodesMap[m]||[]).filter(n => n !== nodeName);
      }
      console.log("UNLABEL nodesMap[metric] " + nodesMap[metric] + " for " + metric);
    }
    updateLocalProgress();
}

// Tagify Setup
let input = document.querySelector('#missing-input');
let tagify = new Tagify(input);

// Selection → Popup Logic
let codeBlock = document.querySelector('.code-pre code');
let popup     = document.querySelector('#selection-popup');
let spanText  = document.querySelector('#selected-text');

let lastSelection = '';


document.addEventListener('DOMContentLoaded', () => {
  // Wire up button clicks to capture which action …
  const form = document.querySelector('#annotation_form');
  let clickedAction = null;

  form.querySelectorAll('button[type="submit"]').forEach(btn => {
    btn.addEventListener('click', e => {
      clickedAction = e.currentTarget.value;
    });
  });

  // Intercept the form submit
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (!clickedAction)
      return console.error("No action selected");

    const tags = Array.from(document.querySelectorAll("tag")).map(el => el.getAttribute("value"));
    const notesInput = document.getElementById('notes-input').value;
    const payload = {
      action: clickedAction,
      nodes:  nodesMap,
      missing: tags,
      notes: notesInput,
    };

    console.log("Notes saved: " + notesInput);

    try {
      const resp = await fetch(window.location.pathname, {
        method:      'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      // Flask did a redirect (prev/next)?
      if (resp.redirected) {
        window.location.href = resp.url;
        return;
      }

      // otherwise, assume JSON back
      const result = await resp;

      if (result.ok) {
        console.log("Saved OK");
      } else {
        console.error("Error saving:", result);
      }
    }
    catch(err) {
      console.error("Fetch error: payload " + JSON.stringify(payload))
      console.error("Response: " + resp);
      console.error("Fetch error:", err);
    }
    finally {
      clickedAction = null;
    }
  });

  // selection logic
  codeBlock = document.querySelector('.code-pre code');
  popup     = document.querySelector('#selection-popup');
  spanText  = document.querySelector('#selected-text');

  lastSelection = '';

  document.querySelector('#add-entity-btn').addEventListener('click', () => {
      tagify.addTags([ lastSelection ]);
      hidePopup();
  });

  document.querySelector('#cancel-entity-btn').addEventListener('click', hidePopup);

  document.addEventListener('click', (e) => {
    if (!popup.contains(e.target) && !codeBlock.contains(e.target)) {
      hidePopup();
    }
  });
});


codeBlock.addEventListener('mouseup', (e) => {
  const sel = window.getSelection();
  const txt = sel.toString().trim();

  if (!txt || txt.length > 52)
    return hidePopup();

  const range = sel.getRangeAt(0);
  const rect  = range.getBoundingClientRect();

  lastSelection = txt;
  spanText.textContent = txt;
  popup.style.top  = (rect.bottom + window.scrollY + 5) + 'px';
  popup.style.left = (rect.left + window.scrollX) + 'px';
  popup.style.display = 'block';
});

function hidePopup() {
  popup.style.display = 'none';
  lastSelection = '';
}
