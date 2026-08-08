package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** household-duplicate: the soundex identity key includes the telephone, so
 * two owners with the same lastName and postcode but DIFFERENT telephones are no longer a hard
 * household duplicate. They are created as a soft match (possibleDuplicate true), not rejected with
 * 409 -- the separate household-duplicate block no longer applies once duplicate detection is the
 * single identity key. */
@Tag("cp10")
class Cp10Tests extends AcceptanceBase {

	@Test
	void coreSameLastNameAndPostcodeNoLongerHardDuplicate() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = ownerNode();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		createOwnerOk(a);
		ObjectNode b = ownerNode(); // same lastName + postcode, unique telephone -> soft match, not 409
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		int id = createOwnerOk(b);
		getOwner(id).andExpect(status().isOk())
				.andExpect(jsonPath("$.possibleDuplicate").value(true));
	}
}
