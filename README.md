AER (API is easier to use since it has all the authors and references in structured format)

API data is generally cleaner than the scraped data
Ability to go into DOI for more papers, but some issues with books and working papers not having enough metadata to include

Clarification: High-impact journal references as proportion of all references or journal references?

Ideas on how to store data:
- Unweighted directed citation graph: nodes are papers, edges are citations
- Weighted directed citation graph: nodes are papers, edges are citations, weights are the reciprocal of the number of citations
- Weighted directed citation graph: nodes are authors, edges are citations, weights are the number of citations
- Institution collaboration graph: nodes are institutions, edges are collaborations, weights are the number of collaborations

Each node has high dimensionality in addition to the citation graph relations:
- Author: name, institution, h-index, etc.
- Paper: title, abstract, keywords, etc.
- Institution: name, location, etc.

Considerations:
- Author affiliation at the time of publication vs now
- Author h-index from Google Scholar

Downstream tasks:
- Graph clustering: cluster papers into different fields based on the citation graph
    - node2vec can be used to take edges and embed the nodes in a low-dimensional space (simulated biased random walks)
    - embedding of abstract data can be used to cluster papers into different fields (SciBERT and then t-sne)
- Link prediction: suggest citations or collaborators for a given paper or author
    - use graph autoencoders to embed the citation graph and then use the embeddings to predict the links
    - https://research.facebook.com/publications/revisiting-graph-neural-networks-for-link-prediction/
- Clique detection: detect communities or groups of papers that are densely connected, as well as the density of the communities
    - use maximal clique detection algorithm
    - try setting parameter for size to 2, 3, 4 to look for tit-for-tat citations or groups of papers

Possible applications:
- Tool for new tenure-track academics to find collaborators in similar fields of interest and two-hop connections

To do:
- Improve searching for papers with title but no DOI to find DOI (for graph creation)
- Parse jsonl files together once all of the journals are done
- What counts as a finance paper?
- Add abstract embeddings to the nodes
- Add author affiliation to the nodes
flag erratum and corrigendum
percentiles for references
QJE
Econometrica
RES
Management Science (hold off on this for now)

merge jerry's dataset to us
cross-check on google scholar
is the field more integrated in how knowledge disperses?
PhD location
employed at time of publication
prefer JEL codes over SciBERT
