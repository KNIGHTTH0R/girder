import $ from 'jquery';
import _ from 'underscore';

import View from 'girder/views/View';
import SearchResultsTemplate from 'girder/templates/widgets/searchResults.pug';

var SearchResultsView = View.extend({
    events: {

    },

    /**
     *
     */
    initialize: function (settings) {
        console.log(settings.length);
        this.results = settings
        for(resource in settings.results) {
        	console.log(resource);
        }
    },

    render: function () {
    	var list = this.$('.g-search-results>ul');
    	list.html(SearchResultsTemplate({
                    results: resources
        }));

    	return this;
    }


});

export default SearchResultsView;