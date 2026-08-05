package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp35 soft-match: a new owner that is not a hard duplicate but shares an existing owner's
 *  lastName and postcode (different telephone) is still created, with 'possibleDuplicate' true and
 *  'possibleDuplicateOf' set to the matching owner id. */
@Tag("cp35")
class Cp35Tests extends AcceptanceBase {

	@Test
	void coreFlagsPossibleDuplicate() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = withPostcode(ownerNode());
		a.put("lastName", lastName);
		int ida = createOwnerOk(a);
		ObjectNode b = withPostcode(ownerNode()); // same postcode + lastName, unique telephone/address
		b.put("lastName", lastName);
		int idb = createOwnerOk(b);
		getOwner(idb).andExpect(jsonPath("$.possibleDuplicate").value(true))
				.andExpect(jsonPath("$.possibleDuplicateOf").value(ida));
	}
}
