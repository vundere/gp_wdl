# gp_wdl
general purpose webcomic downloader  
(quick and dirty readme thrown together because I was bored, most likely missing a bunch and full of errors, just like the script it's written for)

This is a script that aims to work for most webcomics, and uses multiprocessing to maintain a personal library.  
It's written out of a personal desire to archive webcomics I have enjoyed, because I've seen many suddenly disappear from the web without warning.

Due to how multiprocessing works, this is written as a class, because that makes it a lot easier to handle instancing and variables.  
If anyone reading this have suggestions to how this could be rewritten to something better, I'd love to hear it.  
  
How it works(or ideally should, at any rate) is; essentially a naive image scraper, it downloads a bunch of images, then when it has enough to get a decent average size it starts ignoring small images to avoid processing a bunch of button graphics and ads.  
Post-download it deletes all the irrelevant images.


Known weaknesses:
  - Generated webpages
  - Dynamic content (pretty much same as above)
  - Unorthodox domain use / URLs
