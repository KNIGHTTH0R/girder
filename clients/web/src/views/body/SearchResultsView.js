import $ from 'jquery';
import _ from 'underscore';

import View from 'girder/views/View';
import SearchResultsTemplate from 'girder/templates/body/searchResults.pug';

import PaginateWidget from 'girder/views/widgets/PaginateWidget';

var SearchResultsView = View.extend({
    events: {

    },

    /**
     * This view display all the search results per each type
     */
    initialize: function (settings) {
        this.results = [];
/*
        this.paginateWidget = new PaginateWidget({
            collection: ,
            parentView: this
        });
*/
        this.render()
    },

    render: function () {
        this.testfunction();

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
    parse_result: function (rawResults) { // NEED TO BE TEST
        var results = [];
        var collections = [];
        var folders = [];
        var items = [];
        var users = [];
        const types = ['collection','folder','item','user'];
        const icons = ['sitemap','folder','doc-text-inv','user']
        for (result in rawResults) {
            if (result.type === 'collection') {
                collections.push({
                    id: result.id,
                    text: result.text
                });
            } else if (result.type === 'folder') {
                folders.push({
                    id: result.id,
                    text: result.text
                });
            } else if (result.type === 'item') {
                items.push({
                    id: result.id,
                    text: result.text
                });
            } else if (result.type === 'user') {
                users.push({
                    id: result.id,
                    text: result.text
                });
            } else {
                console.log('Error type: '+ result.type + 'inconnu');
            }
        }
        var elements = [collections, folders, items, users];
        for (var k in range(0,3)) {
            results.push({
                type: types[k],
                icon: icons[k],
                elements: elements[k]
            });
        }
        return results;
    },

    testfunction : function () {
        this.results.push({
            type:'collection',
            icon:'sitemap',
            elements: [{
                    id:'59b844a2c9c5cb40b44d57a3',
                    text:'collectionName_1'
                },
                {
                    id:'59b844a2c9c5cb40b44d57a3',
                    text:'collectionName_2'
                },
                {
                    id:'59b844a2c9c5cb40b44d57a3',
                    text:'collectionName_3'
                }]
        });
        this.results.push({
            type:'folder',
            icon:'folder',
            elements: [{
                id:'59b844a2c9c5cb40b44d57a3',
                text:'folderName'
            }]
        });
        this.results.push({
            type:'user',
            icon:'user',
            elements: [{
                id:'59b844a2c9c5cb40b44d57a3',
                text:'userName'
            }]
        });
        this.results.push({
            type:'item',
            icon:'doc-text-inv',
            elements: [{
                id:'59b844a2c9c5cb40b44d57a3',
                text:'itemName'
            }]
        });
    }

});

export default SearchResultsView;
