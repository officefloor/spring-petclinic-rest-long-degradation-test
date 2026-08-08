package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** soft-match: the soft match now triggers on soundex(lastName) + postcode with
 * a differing identityKey. Two owners with the same lastName (same soundex) and postcode, different
 * telephone, flag the second as a possible duplicate of the first. */
@Tag("cp35")
class Cp35Tests extends AcceptanceBase {

	@Test
	void coreSoftMatchOnSoundexAndPostcode() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = withPostcode(ownerNode());
		a.put("lastName", lastName);
		int ida = createOwnerOk(a);
		ObjectNode b = withPostcode(ownerNode());
		b.put("lastName", lastName);
		int idb = createOwnerOk(b);
		getOwner(idb).andExpect(jsonPath("$.possibleDuplicate").value(true))
				.andExpect(jsonPath("$.possibleDuplicateOf").value(ida));
	}
}
