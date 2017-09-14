import $ from 'jquery';
import _ from 'underscore';

import View from 'girder/views/View';
import { restRequest } from 'girder/rest';

import SearchResultsTemplate from 'girder/templates/body/searchResults.pug';

// import PaginateWidget from 'girder/views/widgets/PaginateWidget';

var SearchResultsView = View.extend({
    events: {
        'click .g-search-result>a': function (e) {
            this._resultClicked($(e.currentTarget));
        }
    },

    /**
     * This view display all the search results per each type
     */
    initialize: function (settings) {
        this.ajaxLock = false;
        this.pending = null;
        this.rawResults = [];
        this.results = [];
        this.query = settings.query;
        this.mode = settings.mode;
        this.types = settings.types || ['collection', 'folder', 'item', 'user'];
        // this.paginateWidget = new PaginateWidget({});
        this.search();
    },

    search: function () {
        if (!this.query) {
            // TODO : Special display if the query is empty
            // BUG : if mode 'Prefix' and empty query -----> all is display
            this.render();
        }
        if (this.ajaxLock) {
            this.pending = this.query;
        } else {
            const rawPromise = this._doSearch(this.query);
            rawPromise.done(() => {
                if (this.rawResults.length !== 0) {
                    this.results = this.parse_result(this.rawResults);
                }
                this.render();
            });
        }
    },

    _resultClicked: function (link) {
        console.log('Resource clicked');
        if (link.attr('resourcetype') === 'resultPage') {
            this._goToResultPage(this.$('.g-search-field').val(), this.currentMode);
        } else {
            this.trigger('g:resultClicked', {
                type: link.attr('resourcetype'),
                id: link.attr('resourceid'),
                text: link.text().trim(),
                icon: link.attr('g-icon')
            });
        }
    },

    render: function () {
        this.$el.html(SearchResultsTemplate({
            results: this.results || null
        }));

        return this;
    },

    /**
     * This function has to convert the result object from the searchFieldWidget
     * to an object like :
     *      results = [{
     *          type: type,
     *          icon: icon_type,
     *          elements: [{
     *              id: obj_id,
     *              text: obj_name
     *          }, ...]
     *      }, ...]
     * which contain each results with the same type in the same list 'elements'.
     */
    parse_result: function (rawResults) {
        var results = [];
        var collections = [];
        var folders = [];
        var items = [];
        var users = [];
        var elements = [];
        const icons = ['sitemap', 'folder', 'doc-text-inv', 'user'];
        rawResults.forEach((result) => {
            if (result.type === 'collection') {
                collections.push(result);
            } else if (result.type === 'folder') {
                folders.push(result);
            } else if (result.type === 'item') {
                items.push(result);
            } else if (result.type === 'user') {
                users.push(result);
            } else {
                console.log('Error type: ' + result.type + 'inconnu');
            }
        });
        var resultsTypes = [collections, folders, items, users];
        for (var k = 0; k < resultsTypes.length; k++) {
            resultsTypes[k].forEach((element) => {
                elements.push({
                    id: element.id,
                    text: element.text
                });
            });
            if (elements.length !== 0) {
                results.push({
                    type: this.types[k],
                    icon: icons[k],
                    elements: elements
                });
            }
            elements = [];
        }
        return results;
    },

    _doSearch: function (q) {
        this.ajaxLock = true;
        this.pending = null;

        const rawResultsPromise = restRequest({
            url: 'resource/search',
            data: {
                q: q,
                mode: this.mode,
                types: JSON.stringify(this.types)
            }
        }).done(_.bind(function (results) {
            this.ajaxLock = false;

            if (this.pending) {
                this._doSearch(this.pending);
            } else {
                var resources = [];
                _.each(this.types, function (type) {
                    _.each(results[type] || [], function (result) {
                        var text, icon;
                        if (type === 'user') {
                            text = result.firstName + ' ' + result.lastName +
                                ' (' + result.login + ')';
                            icon = 'user';
                        } else if (type === 'group') {
                            text = result.name;
                            icon = 'users';
                        } else if (type === 'collection') {
                            text = result.name;
                            icon = 'sitemap';
                        } else if (type === 'folder') {
                            text = result.name;
                            icon = 'folder';
                        } else if (type === 'item') {
                            text = result.name;
                            icon = 'doc-text-inv';
                        } else {
                            if (!text || !icon) {
                                text = '[unknown type]';
                                icon = 'attention';
                            }
                        }
                        resources.push({
                            type: type,
                            id: result._id,
                            text: text,
                            icon: icon
                        });
                    }, this);
                }, this);
                this.rawResults = resources;
            }
        }, this));
        return rawResultsPromise;
    }
});

export default SearchResultsView;
