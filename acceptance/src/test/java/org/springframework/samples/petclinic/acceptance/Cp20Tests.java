package org.springframework.samples.petclinic.acceptance;

import java.time.DayOfWeek;
import java.time.LocalDate;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp20 business-day: the default registration date must fall on a business day (a weekend rolls
 *  forward to Monday). Can't force the server's clock black-box, so assert the invariant that holds
 *  every day: the default registrationDate is never a Saturday or Sunday. */
@Tag("cp20")
class Cp20Tests extends AcceptanceBase {

	@Test
	void coreDefaultDateIsBusinessDay() throws Exception {
		int id = createOwnerOk(ownerNode());
		DayOfWeek dow = LocalDate.parse(fetchOwner(id).get("registrationDate").asText()).getDayOfWeek();
		assertTrue(dow != DayOfWeek.SATURDAY && dow != DayOfWeek.SUNDAY, dow.toString());
	}
}
